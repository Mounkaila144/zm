import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zarma_mobile/features/contribution/application/consent_controller.dart';
import 'package:zarma_mobile/models/recognition_result.dart';
import 'package:zarma_mobile/network/api_client.dart';
import 'package:zarma_mobile/recording/audio_recording_models.dart';

enum RecognitionFailureType {
  timeout,
  noConnection,
  cancelled,
  invalidAudio,
  rateLimited,
  serviceUnavailable,
  consentRequired,
  updateRequired,
  invalidResponse,
  badCertificate,
  unknown,
}

class RecognitionFailure implements Exception {
  const RecognitionFailure({
    required this.type,
    required this.message,
    this.statusCode,
    this.code,
    this.requestId,
  });

  final RecognitionFailureType type;
  final String message;
  final int? statusCode;
  final String? code;
  final String? requestId;

  bool get isCancelled => type == RecognitionFailureType.cancelled;

  @override
  String toString() => message;
}

abstract interface class RecognitionRepository {
  Future<RecognitionResult> recognize({
    required AudioHandoff handoff,
    required String anonId,
    required CancelToken cancelToken,
  });
}

class DioRecognitionRepository implements RecognitionRepository {
  const DioRecognitionRepository(this._dio, {this.consentId = ''});

  final Dio _dio;
  final String consentId;

  @override
  Future<RecognitionResult> recognize({
    required AudioHandoff handoff,
    required String anonId,
    required CancelToken cancelToken,
  }) async {
    try {
      final MultipartFile audio = await MultipartFile.fromFile(
        handoff.path,
        filename: _wavFilename(handoff.path),
        contentType: DioMediaType.parse('audio/wav'),
      );
      final FormData body = FormData.fromMap(<String, dynamic>{
        'audio': audio,
        'anon_id': anonId,
        'consent_id': consentId,
      });
      final Response<dynamic> response = await _dio.post<dynamic>(
        '/recognize',
        data: body,
        cancelToken: cancelToken,
      );
      final Object? data = response.data;
      if (data is! Map<String, dynamic>) {
        throw const RecognitionContractException();
      }
      return RecognitionResult.fromLiveJson(data);
    } on DioException catch (error) {
      throw _recognitionFailure(normalizeNetworkFailure(error));
    } on RecognitionContractException {
      throw const RecognitionFailure(
        type: RecognitionFailureType.invalidResponse,
        message: 'La réponse du service est invalide.',
      );
    } on RecognitionFailure {
      rethrow;
    } catch (error, stackTrace) {
      if (kDebugMode) {
        debugPrint('Recognition request failed unexpectedly: $error');
        debugPrintStack(stackTrace: stackTrace);
      }
      throw const RecognitionFailure(
        type: RecognitionFailureType.unknown,
        message: 'Le service n’a pas pu traiter la demande.',
      );
    }
  }
}

final recognitionRepositoryProvider = Provider<RecognitionRepository>((ref) {
  return DioRecognitionRepository(
    ref.watch(dioProvider),
    consentId: ref.watch(consentStatusProvider).acceptance?.id ?? '',
  );
});

RecognitionFailure _recognitionFailure(NetworkFailure failure) {
  final int? status = failure.statusCode;
  final String? code = failure.code;
  final RecognitionFailureType type;
  final String message;

  if (failure.type == NetworkFailureType.cancelled) {
    type = RecognitionFailureType.cancelled;
    message = '';
  } else if (failure.type == NetworkFailureType.timeout ||
      status == 504 ||
      code == 'TIMEOUT') {
    type = RecognitionFailureType.timeout;
    message = 'Le traitement a pris trop de temps.';
  } else if (failure.type == NetworkFailureType.noConnection) {
    type = RecognitionFailureType.noConnection;
    message = 'Impossible de joindre le serveur.';
  } else if (failure.type == NetworkFailureType.unknown &&
      failure.message == 'La connexion sécurisée a échoué.') {
    type = RecognitionFailureType.badCertificate;
    message = 'La connexion sécurisée a échoué.';
  } else if (status == 400 || status == 413 || status == 422) {
    type = RecognitionFailureType.invalidAudio;
    message = 'L’enregistrement n’a pas pu être traité.';
  } else if (status == 403 || code == 'CONSENT_INVALID') {
    type = RecognitionFailureType.consentRequired;
    message = 'Votre accord doit être renouvelé.';
  } else if (status == 426 || code == 'APP_UPDATE_REQUIRED') {
    type = RecognitionFailureType.updateRequired;
    message = 'Une mise à jour de l’application est obligatoire.';
  } else if (status == 429 || code == 'RATE_LIMITED') {
    type = RecognitionFailureType.rateLimited;
    message = 'Trop de demandes. Patientez avant de recommencer.';
  } else if (status == 500 || status == 503) {
    type = RecognitionFailureType.serviceUnavailable;
    message = 'Le service est momentanément indisponible.';
  } else {
    type = RecognitionFailureType.unknown;
    message = 'Le service n’a pas pu traiter la demande.';
  }

  return RecognitionFailure(
    type: type,
    message: message,
    statusCode: status,
    code: code,
    requestId: failure.requestId,
  );
}

String _wavFilename(String path) {
  final String filename = path.split('/').last;
  return filename.toLowerCase().endsWith('.wav') ? filename : '$filename.wav';
}
