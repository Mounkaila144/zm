import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zarma_mobile/network/api_client.dart';

class ConsentContent {
  const ConsentContent({
    required this.consentVersion,
    required this.text,
  });

  factory ConsentContent.fromJson(Map<String, dynamic> json) {
    final Object? version = json['consent_version'];
    final Object? text = json['text'];
    if (version is! String ||
        version.trim().isEmpty ||
        text is! String ||
        text.trim().isEmpty) {
      throw const ConsentContractException();
    }
    return ConsentContent(consentVersion: version, text: text);
  }

  final String consentVersion;
  final String text;
}

class ConsentAcceptance {
  const ConsentAcceptance({
    required this.id,
    required this.anonId,
    required this.consentVersion,
    required this.acceptedAt,
    required this.withdrawn,
  });

  factory ConsentAcceptance.fromJson(Map<String, dynamic> json) {
    final Object? id = json['id'];
    final Object? anonId = json['anon_id'];
    final Object? version = json['consent_version'];
    final Object? acceptedAt = json['accepted_at'];
    final Object? withdrawn = json['withdrawn'];
    if (id is! String ||
        id.trim().isEmpty ||
        anonId is! String ||
        anonId.trim().isEmpty ||
        version is! String ||
        version.trim().isEmpty ||
        acceptedAt is! String ||
        withdrawn is! bool) {
      throw const ConsentContractException();
    }
    final DateTime? timestamp = DateTime.tryParse(acceptedAt);
    if (timestamp == null) {
      throw const ConsentContractException();
    }
    return ConsentAcceptance(
      id: id,
      anonId: anonId,
      consentVersion: version,
      acceptedAt: timestamp,
      withdrawn: withdrawn,
    );
  }

  final String id;
  final String anonId;
  final String consentVersion;
  final DateTime acceptedAt;
  final bool withdrawn;
}

enum ConsentFailureType {
  timeout,
  noConnection,
  cancelled,
  invalidResponse,
  unavailable,
}

class ConsentFailure implements Exception {
  const ConsentFailure({
    required this.type,
    required this.message,
  });

  final ConsentFailureType type;
  final String message;

  bool get isCancelled => type == ConsentFailureType.cancelled;

  @override
  String toString() => message;
}

class ConsentContractException implements Exception {
  const ConsentContractException();
}

abstract interface class ConsentRepository {
  Future<ConsentContent> fetchCurrent({required CancelToken cancelToken});

  Future<ConsentAcceptance> accept({
    required String anonId,
    required String consentVersion,
    required CancelToken cancelToken,
  });
}

class DioConsentRepository implements ConsentRepository {
  const DioConsentRepository(this._dio);

  final Dio _dio;

  @override
  Future<ConsentContent> fetchCurrent({
    required CancelToken cancelToken,
  }) async {
    try {
      final Response<dynamic> response = await _dio.get<dynamic>(
        '/consent',
        cancelToken: cancelToken,
      );
      return ConsentContent.fromJson(_jsonObject(response.data));
    } on DioException catch (error) {
      throw _consentFailure(normalizeNetworkFailure(error));
    } on ConsentContractException {
      throw const ConsentFailure(
        type: ConsentFailureType.invalidResponse,
        message: 'Le texte de consentement est indisponible.',
      );
    }
  }

  @override
  Future<ConsentAcceptance> accept({
    required String anonId,
    required String consentVersion,
    required CancelToken cancelToken,
  }) async {
    try {
      final Response<dynamic> response = await _dio.post<dynamic>(
        '/consent',
        data: <String, dynamic>{
          'anon_id': anonId,
          'consent_version': consentVersion,
        },
        cancelToken: cancelToken,
      );
      final ConsentAcceptance receipt =
          ConsentAcceptance.fromJson(_jsonObject(response.data));
      if (receipt.anonId != anonId ||
          receipt.consentVersion != consentVersion ||
          receipt.withdrawn) {
        throw const ConsentContractException();
      }
      return receipt;
    } on DioException catch (error) {
      throw _consentFailure(normalizeNetworkFailure(error));
    } on ConsentContractException {
      throw const ConsentFailure(
        type: ConsentFailureType.invalidResponse,
        message: 'Le consentement n’a pas pu être confirmé.',
      );
    }
  }
}

final Provider<ConsentRepository> consentRepositoryProvider =
    Provider<ConsentRepository>((ref) {
  return DioConsentRepository(ref.watch(dioProvider));
});

Map<String, dynamic> _jsonObject(Object? value) {
  if (value is! Map<String, dynamic>) {
    throw const ConsentContractException();
  }
  return value;
}

ConsentFailure _consentFailure(NetworkFailure failure) {
  switch (failure.type) {
    case NetworkFailureType.timeout:
      return const ConsentFailure(
        type: ConsentFailureType.timeout,
        message: 'Le serveur met trop de temps à répondre.',
      );
    case NetworkFailureType.noConnection:
      return const ConsentFailure(
        type: ConsentFailureType.noConnection,
        message: 'Impossible de charger le consentement.',
      );
    case NetworkFailureType.cancelled:
      return const ConsentFailure(
        type: ConsentFailureType.cancelled,
        message: '',
      );
    case NetworkFailureType.badResponse:
    case NetworkFailureType.unknown:
      return const ConsentFailure(
        type: ConsentFailureType.unavailable,
        message: 'Le service de consentement est momentanément indisponible.',
      );
  }
}
