import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zarma_mobile/config/app_config.dart';

Dio createDio(AppConfig config) {
  return Dio(
    BaseOptions(
      baseUrl: config.apiBaseUrl,
      headers: const <String, dynamic>{
        'X-App-Build': AppConfig.buildNumber,
      },
      connectTimeout: config.connectTimeout,
      sendTimeout: config.sendTimeout,
      receiveTimeout: config.receiveTimeout,
    ),
  );
}

final dioProvider = Provider<Dio>((ref) {
  return createDio(ref.watch(appConfigProvider));
});

enum NetworkFailureType {
  timeout,
  noConnection,
  cancelled,
  badResponse,
  unknown,
}

class NetworkFailure implements Exception {
  const NetworkFailure({
    required this.type,
    required this.message,
    this.statusCode,
    this.code,
    this.requestId,
  });

  final NetworkFailureType type;
  final String message;
  final int? statusCode;
  final String? code;
  final String? requestId;

  @override
  String toString() => message;
}

NetworkFailure normalizeNetworkFailure(DioException exception) {
  switch (exception.type) {
    case DioExceptionType.connectionTimeout:
    case DioExceptionType.sendTimeout:
    case DioExceptionType.receiveTimeout:
      return const NetworkFailure(
        type: NetworkFailureType.timeout,
        message: 'Le serveur met trop de temps à répondre.',
      );
    case DioExceptionType.connectionError:
      return const NetworkFailure(
        type: NetworkFailureType.noConnection,
        message: 'Impossible de joindre le serveur.',
      );
    case DioExceptionType.cancel:
      return const NetworkFailure(
        type: NetworkFailureType.cancelled,
        message: 'La requête a été annulée.',
      );
    case DioExceptionType.badResponse:
      final Map<String, dynamic>? error = _apiError(exception.response?.data);
      return NetworkFailure(
        type: NetworkFailureType.badResponse,
        message: 'Le serveur ne peut pas traiter la demande.',
        statusCode: exception.response?.statusCode,
        code: error?['code'] as String?,
        requestId: error?['request_id'] as String?,
      );
    case DioExceptionType.badCertificate:
      return const NetworkFailure(
        type: NetworkFailureType.unknown,
        message: 'La connexion sécurisée a échoué.',
      );
    case DioExceptionType.unknown:
      if (exception.error is SocketException) {
        return const NetworkFailure(
          type: NetworkFailureType.noConnection,
          message: 'Impossible de joindre le serveur.',
        );
      }
      return const NetworkFailure(
        type: NetworkFailureType.unknown,
        message: 'Une erreur réseau est survenue.',
      );
  }
}

CancelToken createCancelToken() => CancelToken();

Map<String, dynamic>? _apiError(Object? data) {
  if (data is! Map<String, dynamic>) {
    return null;
  }
  final Object? error = data['error'];
  return error is Map<String, dynamic> ? error : null;
}
