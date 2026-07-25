import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zarma_mobile/features/contribution/models/contribution_models.dart';
import 'package:zarma_mobile/network/api_client.dart';

enum ContributionUploadFailureType {
  timeout,
  noConnection,
  cancelled,
  invalidConsent,
  invalidContribution,
  rateLimited,
  serviceUnavailable,
  invalidResponse,
  badCertificate,
  unknown,
}

class ContributionUploadFailure implements Exception {
  const ContributionUploadFailure({
    required this.type,
    required this.message,
    this.statusCode,
    this.code,
    this.requestId,
  });

  final ContributionUploadFailureType type;
  final String message;
  final int? statusCode;
  final String? code;
  final String? requestId;

  bool get isCancelled => type == ContributionUploadFailureType.cancelled;

  @override
  String toString() => message;
}

class ContributionReceipt {
  const ContributionReceipt({
    required this.id,
    required this.status,
    required this.expectedNumber,
    required this.expectedPrompt,
    required this.modelVersion,
    required this.grammarVersion,
    required this.createdAt,
  });

  factory ContributionReceipt.fromJson(Map<String, dynamic> json) {
    final Object? id = json['id'];
    final Object? status = json['status'];
    final Object? expectedNumber = json['expected_number'];
    final Object? expectedPrompt = json['expected_prompt'];
    final Object? modelVersion = json['model_version'];
    final Object? grammarVersion = json['grammar_version'];
    final Object? createdAt = json['created_at'];
    final DateTime? parsedCreatedAt =
        createdAt is String ? DateTime.tryParse(createdAt) : null;
    if (id is! String ||
        id.isEmpty ||
        status != 'pending' ||
        expectedNumber is! int ||
        expectedPrompt is! String ||
        expectedPrompt.isEmpty ||
        modelVersion is! String ||
        modelVersion.isEmpty ||
        grammarVersion is! String ||
        grammarVersion.isEmpty ||
        parsedCreatedAt == null) {
      throw const ContributionUploadFailure(
        type: ContributionUploadFailureType.invalidResponse,
        message: 'Le reçu de contribution est invalide.',
      );
    }
    return ContributionReceipt(
      id: id,
      status: 'pending',
      expectedNumber: expectedNumber,
      expectedPrompt: expectedPrompt,
      modelVersion: modelVersion,
      grammarVersion: grammarVersion,
      createdAt: parsedCreatedAt,
    );
  }

  final String id;
  final String status;
  final int expectedNumber;
  final String expectedPrompt;
  final String modelVersion;
  final String grammarVersion;
  final DateTime createdAt;
}

abstract interface class ContributionUploadRepository {
  Future<ContributionReceipt> upload({
    required PendingContribution contribution,
    required CancelToken cancelToken,
  });
}

class DioContributionUploadRepository implements ContributionUploadRepository {
  const DioContributionUploadRepository(this._dio);

  final Dio _dio;

  @override
  Future<ContributionReceipt> upload({
    required PendingContribution contribution,
    required CancelToken cancelToken,
  }) async {
    try {
      final MultipartFile audio = await MultipartFile.fromFile(
        contribution.audio.path,
        filename: 'contribution.wav',
        contentType: DioMediaType.parse('audio/wav'),
      );
      final Map<String, dynamic> fields = <String, dynamic>{
        'audio': audio,
        'consent_id': contribution.consentId,
        'anon_id': contribution.anonId,
        'expected_number': contribution.expectedNumber,
        'expected_prompt': contribution.expectedPrompt,
        'grammar_version': contribution.grammarVersion,
      };
      if (contribution.region != null) {
        fields['region'] = contribution.region;
      }
      if (contribution.deviceInfo != null) {
        fields['device_info'] = contribution.deviceInfo;
      }
      final Response<dynamic> response = await _dio.post<dynamic>(
        '/recordings',
        data: FormData.fromMap(fields),
        cancelToken: cancelToken,
      );
      final Object? data = response.data;
      if (data is! Map<String, dynamic>) {
        throw const ContributionUploadFailure(
          type: ContributionUploadFailureType.invalidResponse,
          message: 'Le reçu de contribution est invalide.',
        );
      }
      final ContributionReceipt receipt = ContributionReceipt.fromJson(data);
      if (receipt.expectedNumber != contribution.expectedNumber ||
          receipt.expectedPrompt != contribution.expectedPrompt ||
          receipt.grammarVersion != contribution.grammarVersion) {
        throw const ContributionUploadFailure(
          type: ContributionUploadFailureType.invalidResponse,
          message: 'Le reçu de contribution est incohérent.',
        );
      }
      return receipt;
    } on DioException catch (error) {
      throw _uploadFailure(normalizeNetworkFailure(error));
    } on ContributionUploadFailure {
      rethrow;
    } catch (_) {
      throw const ContributionUploadFailure(
        type: ContributionUploadFailureType.unknown,
        message: 'La contribution n’a pas pu être envoyée.',
      );
    }
  }
}

final contributionUploadRepositoryProvider =
    Provider<ContributionUploadRepository>((ref) {
  return DioContributionUploadRepository(ref.watch(dioProvider));
});

ContributionUploadFailure _uploadFailure(NetworkFailure failure) {
  final int? status = failure.statusCode;
  final String? code = failure.code;
  final ContributionUploadFailureType type;
  final String message;

  if (failure.type == NetworkFailureType.cancelled) {
    type = ContributionUploadFailureType.cancelled;
    message = 'Envoi annulé.';
  } else if (failure.type == NetworkFailureType.timeout) {
    type = ContributionUploadFailureType.timeout;
    message = 'L’envoi a pris trop de temps.';
  } else if (failure.type == NetworkFailureType.noConnection) {
    type = ContributionUploadFailureType.noConnection;
    message = 'Impossible de joindre le serveur.';
  } else if (failure.type == NetworkFailureType.unknown &&
      failure.message == 'La connexion sécurisée a échoué.') {
    type = ContributionUploadFailureType.badCertificate;
    message = 'La connexion sécurisée a échoué.';
  } else if (status == 403 || code == 'CONSENT_INVALID') {
    type = ContributionUploadFailureType.invalidConsent;
    message = 'Le consentement doit être renouvelé avant l’envoi.';
  } else if (status == 400 || status == 413 || status == 422) {
    type = ContributionUploadFailureType.invalidContribution;
    message = 'L’enregistrement ou ses informations sont invalides.';
  } else if (status == 429 || code == 'RATE_LIMITED') {
    type = ContributionUploadFailureType.rateLimited;
    message = 'Trop d’envois. Patientez avant de recommencer.';
  } else if (status == 500 || status == 503) {
    type = ContributionUploadFailureType.serviceUnavailable;
    message = 'Le service est momentanément indisponible.';
  } else {
    type = ContributionUploadFailureType.unknown;
    message = 'La contribution n’a pas pu être envoyée.';
  }

  return ContributionUploadFailure(
    type: type,
    message: message,
    statusCode: status,
    code: code,
    requestId: failure.requestId,
  );
}
