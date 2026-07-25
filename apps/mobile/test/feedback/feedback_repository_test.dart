import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:zarma_mobile/feedback/feedback_models.dart';
import 'package:zarma_mobile/feedback/feedback_repository.dart';

class MockDio extends Mock implements Dio {}

const String _recognitionId = '11111111-1111-4111-8111-111111111111';
const String _anonId = '22222222-2222-4222-8222-222222222222';
const String _feedbackId = '33333333-3333-4333-8333-333333333333';
const String _modelVersion = 'mock-1.0.0';
const String _grammarVersion = '1.0.0';

void main() {
  late MockDio dio;
  late DioFeedbackRepository repository;

  setUp(() {
    dio = MockDio();
    repository = DioFeedbackRepository(dio);
  });

  void stubResponse(Map<String, dynamic> data, {int status = 201}) {
    when(
      () => dio.post<dynamic>(
        any(),
        data: any(named: 'data'),
        cancelToken: any(named: 'cancelToken'),
      ),
    ).thenAnswer(
      (_) async => Response<dynamic>(
        requestOptions: RequestOptions(path: '/feedback'),
        statusCode: status,
        data: data,
      ),
    );
  }

  void stubThrow(Object error) {
    when(
      () => dio.post<dynamic>(
        any(),
        data: any(named: 'data'),
        cancelToken: any(named: 'cancelToken'),
      ),
    ).thenThrow(error);
  }

  test('poste le body confirmed exact sans versions et valide le receipt',
      () async {
    stubResponse(_receipt());
    final CancelToken token = CancelToken();

    final FeedbackResponse response = await repository.submit(
      request: _request(FeedbackType.confirmed, proposedNumber: 42),
      expectedModelVersion: _modelVersion,
      expectedGrammarVersion: _grammarVersion,
      cancelToken: token,
    );

    expect(response.id, _feedbackId);
    expect(response.feedbackType, FeedbackType.confirmed);
    expect(response.modelVersion, _modelVersion);
    expect(response.grammarVersion, _grammarVersion);

    final List<dynamic> captured = verify(
      () => dio.post<dynamic>(
        '/feedback',
        data: captureAny(named: 'data'),
        cancelToken: captureAny(named: 'cancelToken'),
      ),
    ).captured;
    final Map<String, dynamic> body = captured[0] as Map<String, dynamic>;
    expect(body, <String, dynamic>{
      'recognition_id': _recognitionId,
      'anon_id': _anonId,
      'feedback_type': 'confirmed',
      'proposed_number': 42,
      'corrected_number': null,
    });
    expect(body.containsKey('model_version'), isFalse);
    expect(body.containsKey('grammar_version'), isFalse);
    expect(captured[1], same(token));
  });

  test('poste le body repeat_requested avec proposed_number nullable',
      () async {
    stubResponse(
      _receipt(feedbackType: 'repeat_requested', proposedNumber: null),
    );

    await repository.submit(
      request: _request(FeedbackType.repeatRequested),
      expectedModelVersion: _modelVersion,
      expectedGrammarVersion: _grammarVersion,
      cancelToken: CancelToken(),
    );

    final Map<String, dynamic> body = verify(
      () => dio.post<dynamic>(
        '/feedback',
        data: captureAny(named: 'data'),
        cancelToken: any(named: 'cancelToken'),
      ),
    ).captured.single as Map<String, dynamic>;
    expect(body['feedback_type'], 'repeat_requested');
    expect(body['proposed_number'], isNull);
    expect(body['corrected_number'], isNull);
  });

  test('rejette un receipt dont les versions divergent', () async {
    stubResponse(_receipt(grammarVersion: '9.9.9'));

    await expectLater(
      repository.submit(
        request: _request(FeedbackType.confirmed, proposedNumber: 42),
        expectedModelVersion: _modelVersion,
        expectedGrammarVersion: _grammarVersion,
        cancelToken: CancelToken(),
      ),
      throwsA(
        isA<FeedbackFailure>().having(
          (FeedbackFailure e) => e.type,
          'type',
          FeedbackFailureType.invalidResponse,
        ),
      ),
    );
  });

  test('rejette un receipt dont le nombre proposé diverge', () async {
    stubResponse(_receipt(proposedNumber: 7));

    await expectLater(
      repository.submit(
        request: _request(FeedbackType.confirmed, proposedNumber: 42),
        expectedModelVersion: _modelVersion,
        expectedGrammarVersion: _grammarVersion,
        cancelToken: CancelToken(),
      ),
      throwsA(
        isA<FeedbackFailure>().having(
          (FeedbackFailure e) => e.type,
          'type',
          FeedbackFailureType.invalidResponse,
        ),
      ),
    );
  });

  test('rejette un receipt mal formé', () async {
    final Map<String, dynamic> malformed = _receipt()..remove('created_at');
    stubResponse(malformed);

    await expectLater(
      repository.submit(
        request: _request(FeedbackType.confirmed, proposedNumber: 42),
        expectedModelVersion: _modelVersion,
        expectedGrammarVersion: _grammarVersion,
        cancelToken: CancelToken(),
      ),
      throwsA(
        isA<FeedbackFailure>().having(
          (FeedbackFailure e) => e.type,
          'type',
          FeedbackFailureType.invalidResponse,
        ),
      ),
    );
  });

  test('conserve code et request_id sans message backend brut', () async {
    stubThrow(
      DioException.badResponse(
        statusCode: 404,
        requestOptions: RequestOptions(path: '/feedback'),
        response: Response<dynamic>(
          requestOptions: RequestOptions(path: '/feedback'),
          statusCode: 404,
          data: <String, dynamic>{
            'error': <String, dynamic>{
              'code': 'RECOGNITION_NOT_FOUND',
              'message': 'secret backend detail',
              'request_id': 'req-404',
            },
          },
        ),
      ),
    );

    await expectLater(
      repository.submit(
        request: _request(FeedbackType.confirmed, proposedNumber: 42),
        expectedModelVersion: _modelVersion,
        expectedGrammarVersion: _grammarVersion,
        cancelToken: CancelToken(),
      ),
      throwsA(
        isA<FeedbackFailure>()
            .having((FeedbackFailure e) => e.type, 'type',
                FeedbackFailureType.recognitionNotFound)
            .having((FeedbackFailure e) => e.statusCode, 'status', 404)
            .having((FeedbackFailure e) => e.code, 'code',
                'RECOGNITION_NOT_FOUND')
            .having(
                (FeedbackFailure e) => e.requestId, 'request', 'req-404')
            .having((FeedbackFailure e) => e.message, 'message',
                isNot(contains('secret'))),
      ),
    );
  });

  final Map<int, FeedbackFailureType> statusMappings = <int, FeedbackFailureType>{
    404: FeedbackFailureType.recognitionNotFound,
    422: FeedbackFailureType.validation,
    429: FeedbackFailureType.rateLimited,
    500: FeedbackFailureType.serviceUnavailable,
    503: FeedbackFailureType.serviceUnavailable,
  };
  for (final MapEntry<int, FeedbackFailureType> mapping
      in statusMappings.entries) {
    test('mappe HTTP ${mapping.key} vers ${mapping.value.name}', () async {
      stubThrow(
        DioException.badResponse(
          statusCode: mapping.key,
          requestOptions: RequestOptions(path: '/feedback'),
          response: Response<dynamic>(
            requestOptions: RequestOptions(path: '/feedback'),
            statusCode: mapping.key,
          ),
        ),
      );

      await expectLater(
        repository.submit(
          request: _request(FeedbackType.confirmed, proposedNumber: 42),
          expectedModelVersion: _modelVersion,
          expectedGrammarVersion: _grammarVersion,
          cancelToken: CancelToken(),
        ),
        throwsA(
          isA<FeedbackFailure>()
              .having((FeedbackFailure e) => e.type, 'type', mapping.value),
        ),
      );
    });
  }

  test('mappe timeout, absence réseau, certificat et annulation', () async {
    Future<void> verifyType(
      DioExceptionType dioType,
      FeedbackFailureType expected,
    ) async {
      reset(dio);
      stubThrow(
        DioException(
          requestOptions: RequestOptions(path: '/feedback'),
          type: dioType,
        ),
      );
      await expectLater(
        repository.submit(
          request: _request(FeedbackType.confirmed, proposedNumber: 42),
          expectedModelVersion: _modelVersion,
          expectedGrammarVersion: _grammarVersion,
          cancelToken: CancelToken(),
        ),
        throwsA(
          isA<FeedbackFailure>().having(
            (FeedbackFailure e) => e.type,
            'type',
            expected,
          ),
        ),
      );
    }

    await verifyType(
      DioExceptionType.receiveTimeout,
      FeedbackFailureType.timeout,
    );
    await verifyType(
      DioExceptionType.connectionError,
      FeedbackFailureType.noConnection,
    );
    await verifyType(
      DioExceptionType.badCertificate,
      FeedbackFailureType.badCertificate,
    );
    await verifyType(
      DioExceptionType.cancel,
      FeedbackFailureType.cancelled,
    );
  });
}

FeedbackRequest _request(FeedbackType type, {int? proposedNumber}) {
  return FeedbackRequest(
    recognitionId: _recognitionId,
    anonId: _anonId,
    feedbackType: type,
    proposedNumber: proposedNumber,
  );
}

Map<String, dynamic> _receipt({
  String feedbackType = 'confirmed',
  int? proposedNumber = 42,
  String modelVersion = _modelVersion,
  String grammarVersion = _grammarVersion,
}) {
  return <String, dynamic>{
    'id': _feedbackId,
    'recognition_id': _recognitionId,
    'anon_id': _anonId,
    'feedback_type': feedbackType,
    'proposed_number': proposedNumber,
    'corrected_number': null,
    'model_version': modelVersion,
    'grammar_version': grammarVersion,
    'created_at': '2026-07-24T00:00:00Z',
  };
}
