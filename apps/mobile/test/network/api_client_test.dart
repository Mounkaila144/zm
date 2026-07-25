import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:zarma_mobile/config/app_config.dart';
import 'package:zarma_mobile/network/api_client.dart';

void main() {
  const AppConfig config = AppConfig(
    apiBaseUrl: 'http://192.0.2.10:8080/api/v1',
    connectTimeout: Duration(seconds: 7),
    sendTimeout: Duration(seconds: 17),
    receiveTimeout: Duration(seconds: 23),
  );

  test('dio reçoit l’URL et les timeouts de la configuration injectée', () {
    final ProviderContainer container = ProviderContainer(
      overrides: <Override>[
        appConfigProvider.overrideWithValue(config),
      ],
    );
    addTearDown(container.dispose);

    final Dio dio = container.read(dioProvider);

    expect(dio.options.baseUrl, config.apiBaseUrl);
    expect(dio.options.connectTimeout, config.connectTimeout);
    expect(dio.options.sendTimeout, config.sendTimeout);
    expect(dio.options.receiveTimeout, config.receiveTimeout);
  });

  group('normalizeNetworkFailure', () {
    final RequestOptions request = RequestOptions(path: '/health');

    test('normalise les timeouts sans exposer le détail interne', () {
      for (final DioExceptionType type in <DioExceptionType>[
        DioExceptionType.connectionTimeout,
        DioExceptionType.sendTimeout,
        DioExceptionType.receiveTimeout,
      ]) {
        final NetworkFailure failure = normalizeNetworkFailure(
          DioException(
            requestOptions: request,
            type: type,
            message: 'internal-hostname.example',
          ),
        );

        expect(failure.type, NetworkFailureType.timeout);
        expect(failure.toString(), isNot(contains('internal-hostname')));
      }
    });

    test('normalise une absence de réseau', () {
      final NetworkFailure failure = normalizeNetworkFailure(
        DioException(
          requestOptions: request,
          type: DioExceptionType.unknown,
          error: const SocketException('No route to host'),
        ),
      );

      expect(failure.type, NetworkFailureType.noConnection);
      expect(failure.message, 'Impossible de joindre le serveur.');
    });

    test('normalise une annulation', () {
      final NetworkFailure failure = normalizeNetworkFailure(
        DioException(
          requestOptions: request,
          type: DioExceptionType.cancel,
        ),
      );

      expect(failure.type, NetworkFailureType.cancelled);
    });

    test('normalise une réponse en erreur', () {
      final NetworkFailure failure = normalizeNetworkFailure(
        DioException(
          requestOptions: request,
          type: DioExceptionType.badResponse,
          response: Response<void>(
            requestOptions: request,
            statusCode: HttpStatus.serviceUnavailable,
          ),
        ),
      );

      expect(failure.type, NetworkFailureType.badResponse);
      expect(failure.statusCode, HttpStatus.serviceUnavailable);
    });
  });

  test('les futurs appels peuvent être annulés avec un CancelToken Dio', () {
    final CancelToken token = createCancelToken();

    expect(token.isCancelled, isFalse);
    token.cancel();
    expect(token.isCancelled, isTrue);
  });
}
