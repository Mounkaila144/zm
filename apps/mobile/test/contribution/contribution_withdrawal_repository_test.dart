import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:zarma_mobile/features/contribution/data/contribution_withdrawal_repository.dart';

class _MockDio extends Mock implements Dio {}

const String _anonId = '00000000-0000-4000-8000-000000000042';

void main() {
  late _MockDio dio;
  late DioContributionWithdrawalRepository repository;

  setUp(() {
    dio = _MockDio();
    repository = DioContributionWithdrawalRepository(dio);
  });

  test('envoie uniquement anon_id et valide le reçu générique', () async {
    when(
      () => dio.post<dynamic>(
        any(),
        data: any(named: 'data'),
        cancelToken: any(named: 'cancelToken'),
      ),
    ).thenAnswer(
      (_) async => Response<dynamic>(
        requestOptions: RequestOptions(path: '/recordings/withdraw'),
        statusCode: 200,
        data: <String, dynamic>{'status': 'withdrawn'},
      ),
    );
    final CancelToken token = CancelToken();

    await repository.withdraw(anonId: _anonId, cancelToken: token);

    final List<dynamic> captured = verify(
      () => dio.post<dynamic>(
        '/recordings/withdraw',
        data: captureAny(named: 'data'),
        cancelToken: captureAny(named: 'cancelToken'),
      ),
    ).captured;
    expect(
      captured[0],
      <String, dynamic>{'anon_id': _anonId},
    );
    expect(captured[1], same(token));
  });

  test('rejette un reçu incomplet, enrichi ou au mauvais statut', () async {
    Future<void> expectInvalid(Object? body) async {
      reset(dio);
      when(
        () => dio.post<dynamic>(
          any(),
          data: any(named: 'data'),
          cancelToken: any(named: 'cancelToken'),
        ),
      ).thenAnswer(
        (_) async => Response<dynamic>(
          requestOptions: RequestOptions(path: '/recordings/withdraw'),
          statusCode: 200,
          data: body,
        ),
      );

      await expectLater(
        repository.withdraw(anonId: _anonId, cancelToken: CancelToken()),
        throwsA(
          isA<ContributionWithdrawalFailure>().having(
            (e) => e.type,
            'type',
            ContributionWithdrawalFailureType.invalidResponse,
          ),
        ),
      );
    }

    await expectInvalid(<String, dynamic>{});
    await expectInvalid(<String, dynamic>{'status': 'pending'});
    await expectInvalid(<String, dynamic>{
      'status': 'withdrawn',
      'count': 2,
    });
    await expectInvalid('withdrawn');
  });

  final Map<int, ContributionWithdrawalFailureType> statusMappings =
      <int, ContributionWithdrawalFailureType>{
    429: ContributionWithdrawalFailureType.rateLimited,
    500: ContributionWithdrawalFailureType.serviceUnavailable,
    503: ContributionWithdrawalFailureType.incomplete,
  };
  for (final MapEntry<int, ContributionWithdrawalFailureType> mapping
      in statusMappings.entries) {
    test('mappe HTTP ${mapping.key} vers ${mapping.value.name}', () async {
      when(
        () => dio.post<dynamic>(
          any(),
          data: any(named: 'data'),
          cancelToken: any(named: 'cancelToken'),
        ),
      ).thenThrow(
        DioException.badResponse(
          statusCode: mapping.key,
          requestOptions: RequestOptions(path: '/recordings/withdraw'),
          response: Response<dynamic>(
            requestOptions: RequestOptions(path: '/recordings/withdraw'),
            statusCode: mapping.key,
            data: <String, dynamic>{
              'error': <String, dynamic>{
                'code': mapping.key == 503
                    ? 'WITHDRAWAL_INCOMPLETE'
                    : 'SERVER_PRIVATE',
                'message': 'backend secret',
                'request_id': 'request-44',
              },
            },
          ),
        ),
      );

      await expectLater(
        repository.withdraw(anonId: _anonId, cancelToken: CancelToken()),
        throwsA(
          isA<ContributionWithdrawalFailure>()
              .having((e) => e.type, 'type', mapping.value)
              .having((e) => e.requestId, 'requestId', 'request-44')
              .having((e) => e.message, 'message', isNot(contains('secret'))),
        ),
      );
    });
  }

  final Map<DioExceptionType, ContributionWithdrawalFailureType>
      networkMappings = <DioExceptionType, ContributionWithdrawalFailureType>{
    DioExceptionType.receiveTimeout: ContributionWithdrawalFailureType.timeout,
    DioExceptionType.connectionError:
        ContributionWithdrawalFailureType.noConnection,
    DioExceptionType.cancel: ContributionWithdrawalFailureType.cancelled,
  };
  for (final MapEntry<DioExceptionType,
      ContributionWithdrawalFailureType> mapping in networkMappings.entries) {
    test('mappe ${mapping.key.name} vers ${mapping.value.name}', () async {
      when(
        () => dio.post<dynamic>(
          any(),
          data: any(named: 'data'),
          cancelToken: any(named: 'cancelToken'),
        ),
      ).thenThrow(
        DioException(
          requestOptions: RequestOptions(path: '/recordings/withdraw'),
          type: mapping.key,
        ),
      );

      await expectLater(
        repository.withdraw(anonId: _anonId, cancelToken: CancelToken()),
        throwsA(
          isA<ContributionWithdrawalFailure>().having(
            (e) => e.type,
            'type',
            mapping.value,
          ),
        ),
      );
    });
  }
}
