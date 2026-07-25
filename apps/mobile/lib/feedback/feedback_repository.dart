import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zarma_mobile/feedback/feedback_models.dart';
import 'package:zarma_mobile/network/api_client.dart';

enum FeedbackFailureType {
  timeout,
  noConnection,
  cancelled,
  recognitionNotFound,
  validation,
  rateLimited,
  serviceUnavailable,
  invalidResponse,
  badCertificate,
  unknown,
}

class FeedbackFailure implements Exception {
  const FeedbackFailure({
    required this.type,
    required this.message,
    this.statusCode,
    this.code,
    this.requestId,
  });

  final FeedbackFailureType type;
  final String message;
  final int? statusCode;
  final String? code;
  final String? requestId;

  bool get isCancelled => type == FeedbackFailureType.cancelled;

  @override
  String toString() => message;
}

abstract interface class FeedbackRepository {
  /// Envoie un feedback et valide le receipt `201` contre la requête et les
  /// versions de la reconnaissance d'origine. Aucun retry automatique.
  Future<FeedbackResponse> submit({
    required FeedbackRequest request,
    required String expectedModelVersion,
    required String expectedGrammarVersion,
    required CancelToken cancelToken,
  });
}

class DioFeedbackRepository implements FeedbackRepository {
  const DioFeedbackRepository(this._dio);

  final Dio _dio;

  @override
  Future<FeedbackResponse> submit({
    required FeedbackRequest request,
    required String expectedModelVersion,
    required String expectedGrammarVersion,
    required CancelToken cancelToken,
  }) async {
    try {
      final Response<dynamic> response = await _dio.post<dynamic>(
        '/feedback',
        data: request.toJson(),
        cancelToken: cancelToken,
      );
      final Object? data = response.data;
      if (data is! Map<String, dynamic>) {
        throw const FeedbackContractException();
      }
      final FeedbackResponse receipt = FeedbackResponse.fromJson(data);
      _verifyReceipt(
        receipt: receipt,
        request: request,
        expectedModelVersion: expectedModelVersion,
        expectedGrammarVersion: expectedGrammarVersion,
      );
      return receipt;
    } on DioException catch (error) {
      throw _feedbackFailure(normalizeNetworkFailure(error));
    } on FeedbackContractException {
      throw const FeedbackFailure(
        type: FeedbackFailureType.invalidResponse,
        message: 'Le choix n’a pas pu être enregistré.',
      );
    } on FeedbackFailure {
      rethrow;
    } catch (_) {
      throw const FeedbackFailure(
        type: FeedbackFailureType.unknown,
        message: 'Le service n’a pas pu enregistrer le choix.',
      );
    }
  }

  /// Le backend ne valide pas les combinaisons de façon croisée : on refuse
  /// silencieusement tout receipt incohérent côté client.
  void _verifyReceipt({
    required FeedbackResponse receipt,
    required FeedbackRequest request,
    required String expectedModelVersion,
    required String expectedGrammarVersion,
  }) {
    if (receipt.recognitionId != request.recognitionId ||
        receipt.anonId != request.anonId ||
        receipt.feedbackType != request.feedbackType ||
        receipt.proposedNumber != request.proposedNumber ||
        receipt.correctedNumber != request.correctedNumber ||
        receipt.modelVersion != expectedModelVersion ||
        receipt.grammarVersion != expectedGrammarVersion) {
      throw const FeedbackContractException();
    }
  }
}

final feedbackRepositoryProvider = Provider<FeedbackRepository>((ref) {
  return DioFeedbackRepository(ref.watch(dioProvider));
});

FeedbackFailure _feedbackFailure(NetworkFailure failure) {
  final int? status = failure.statusCode;
  final String? code = failure.code;
  final FeedbackFailureType type;
  final String message;

  if (failure.type == NetworkFailureType.cancelled) {
    type = FeedbackFailureType.cancelled;
    message = '';
  } else if (failure.type == NetworkFailureType.timeout) {
    type = FeedbackFailureType.timeout;
    message = 'Impossible d’envoyer le choix pour le moment.';
  } else if (failure.type == NetworkFailureType.noConnection) {
    type = FeedbackFailureType.noConnection;
    message = 'Impossible d’envoyer le choix pour le moment.';
  } else if (failure.type == NetworkFailureType.unknown &&
      failure.message == 'La connexion sécurisée a échoué.') {
    type = FeedbackFailureType.badCertificate;
    message = 'La connexion sécurisée a échoué.';
  } else if (status == 404 || code == 'RECOGNITION_NOT_FOUND') {
    type = FeedbackFailureType.recognitionNotFound;
    message = 'Reconnaissance introuvable. Réenregistrez le nombre.';
  } else if (status == 422 || code == 'VALIDATION_ERROR') {
    type = FeedbackFailureType.validation;
    message = 'Le choix n’a pas pu être enregistré.';
  } else if (status == 429 || code == 'RATE_LIMITED') {
    type = FeedbackFailureType.rateLimited;
    message = 'Trop de demandes. Patientez avant de réessayer.';
  } else if (status == 500 || status == 503) {
    type = FeedbackFailureType.serviceUnavailable;
    message = 'Le service est momentanément indisponible.';
  } else {
    type = FeedbackFailureType.unknown;
    message = 'Le service n’a pas pu enregistrer le choix.';
  }

  return FeedbackFailure(
    type: type,
    message: message,
    statusCode: status,
    code: code,
    requestId: failure.requestId,
  );
}
