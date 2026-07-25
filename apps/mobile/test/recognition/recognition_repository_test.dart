import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:zarma_mobile/models/recognition_result.dart';
import 'package:zarma_mobile/recognition/recognition_repository.dart';
import 'package:zarma_mobile/recording/audio_recording_models.dart';

class MockDio extends Mock implements Dio {}

void main() {
  late MockDio dio;
  late DioRecognitionRepository repository;
  late Directory directory;
  late File audioFile;

  setUp(() async {
    dio = MockDio();
    repository = DioRecognitionRepository(dio);
    directory = await Directory.systemTemp.createTemp('recognition_repo_');
    audioFile = File('${directory.path}/take.wav');
    await audioFile.writeAsBytes(<int>[82, 73, 70, 70]);
  });

  tearDown(() async {
    await directory.delete(recursive: true);
  });

  test('poste le multipart exact avec WAV, UUID et CancelToken', () async {
    when(
      () => dio.post<dynamic>(
        any(),
        data: any(named: 'data'),
        cancelToken: any(named: 'cancelToken'),
      ),
    ).thenAnswer(
      (_) async => Response<dynamic>(
        requestOptions: RequestOptions(path: '/recognize'),
        statusCode: 200,
        data: _response(),
      ),
    );
    final CancelToken token = CancelToken();

    final RecognitionResult result = await repository.recognize(
      handoff: _handoff(audioFile.path),
      anonId: '00000000-0000-4000-8000-0000000000aa',
      cancelToken: token,
    );

    expect(result.decision, Decision.accept);
    final List<dynamic> captured = verify(
      () => dio.post<dynamic>(
        '/recognize',
        data: captureAny(named: 'data'),
        cancelToken: captureAny(named: 'cancelToken'),
      ),
    ).captured;
    final FormData body = captured[0] as FormData;
    expect(body.fields, hasLength(1));
    expect(body.fields.single.key, 'anon_id');
    expect(
      body.fields.single.value,
      '00000000-0000-4000-8000-0000000000aa',
    );
    expect(body.files.single.key, 'audio');
    expect(body.files.single.value.filename, 'take.wav');
    expect(body.files.single.value.contentType.toString(), 'audio/wav');
    expect(captured[1], same(token));
  });

  test('conserve statut, code et request_id sans message backend', () async {
    when(
      () => dio.post<dynamic>(
        any(),
        data: any(named: 'data'),
        cancelToken: any(named: 'cancelToken'),
      ),
    ).thenThrow(
      DioException.badResponse(
        statusCode: 429,
        requestOptions: RequestOptions(path: '/recognize'),
        response: Response<dynamic>(
          requestOptions: RequestOptions(path: '/recognize'),
          statusCode: 429,
          data: <String, dynamic>{
            'error': <String, dynamic>{
              'code': 'RATE_LIMITED',
              'message': 'backend secret detail',
              'request_id': 'request-123',
            },
          },
        ),
      ),
    );

    await expectLater(
      repository.recognize(
        handoff: _handoff(audioFile.path),
        anonId: 'anon',
        cancelToken: CancelToken(),
      ),
      throwsA(
        isA<RecognitionFailure>()
            .having((e) => e.type, 'type', RecognitionFailureType.rateLimited)
            .having((e) => e.statusCode, 'status', 429)
            .having((e) => e.code, 'code', 'RATE_LIMITED')
            .having((e) => e.requestId, 'request', 'request-123')
            .having((e) => e.message, 'message', isNot(contains('secret'))),
      ),
    );
  });

  test('normalise timeout, annulation et réponse mal formée', () async {
    Future<void> expectDioFailure(
      DioException exception,
      RecognitionFailureType expected,
    ) async {
      reset(dio);
      when(
        () => dio.post<dynamic>(
          any(),
          data: any(named: 'data'),
          cancelToken: any(named: 'cancelToken'),
        ),
      ).thenThrow(exception);
      await expectLater(
        repository.recognize(
          handoff: _handoff(audioFile.path),
          anonId: 'anon',
          cancelToken: CancelToken(),
        ),
        throwsA(
          isA<RecognitionFailure>().having((e) => e.type, 'type', expected),
        ),
      );
    }

    await expectDioFailure(
      DioException(
        requestOptions: RequestOptions(path: '/recognize'),
        type: DioExceptionType.receiveTimeout,
      ),
      RecognitionFailureType.timeout,
    );
    await expectDioFailure(
      DioException(
        requestOptions: RequestOptions(path: '/recognize'),
        type: DioExceptionType.cancel,
      ),
      RecognitionFailureType.cancelled,
    );

    reset(dio);
    when(
      () => dio.post<dynamic>(
        any(),
        data: any(named: 'data'),
        cancelToken: any(named: 'cancelToken'),
      ),
    ).thenAnswer(
      (_) async => Response<dynamic>(
        requestOptions: RequestOptions(path: '/recognize'),
        statusCode: 200,
        data: <String, dynamic>{'decision': 'accept'},
      ),
    );
    await expectLater(
      repository.recognize(
        handoff: _handoff(audioFile.path),
        anonId: 'anon',
        cancelToken: CancelToken(),
      ),
      throwsA(
        isA<RecognitionFailure>().having(
          (e) => e.type,
          'type',
          RecognitionFailureType.invalidResponse,
        ),
      ),
    );
  });

  final Map<int, RecognitionFailureType> statusMappings =
      <int, RecognitionFailureType>{
    400: RecognitionFailureType.invalidAudio,
    413: RecognitionFailureType.invalidAudio,
    422: RecognitionFailureType.invalidAudio,
    429: RecognitionFailureType.rateLimited,
    500: RecognitionFailureType.serviceUnavailable,
    503: RecognitionFailureType.serviceUnavailable,
    504: RecognitionFailureType.timeout,
  };
  for (final MapEntry<int, RecognitionFailureType> mapping
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
          requestOptions: RequestOptions(path: '/recognize'),
          response: Response<dynamic>(
            requestOptions: RequestOptions(path: '/recognize'),
            statusCode: mapping.key,
          ),
        ),
      );

      await expectLater(
        repository.recognize(
          handoff: _handoff(audioFile.path),
          anonId: 'anon',
          cancelToken: CancelToken(),
        ),
        throwsA(
          isA<RecognitionFailure>().having(
            (e) => e.type,
            'type',
            mapping.value,
          ),
        ),
      );
    });
  }

  test('mappe absence réseau et certificat', () async {
    Future<void> verifyType(
      DioExceptionType dioType,
      RecognitionFailureType expected,
    ) async {
      reset(dio);
      when(
        () => dio.post<dynamic>(
          any(),
          data: any(named: 'data'),
          cancelToken: any(named: 'cancelToken'),
        ),
      ).thenThrow(
        DioException(
          requestOptions: RequestOptions(path: '/recognize'),
          type: dioType,
        ),
      );
      await expectLater(
        repository.recognize(
          handoff: _handoff(audioFile.path),
          anonId: 'anon',
          cancelToken: CancelToken(),
        ),
        throwsA(
          isA<RecognitionFailure>().having((e) => e.type, 'type', expected),
        ),
      );
    }

    await verifyType(
      DioExceptionType.connectionError,
      RecognitionFailureType.noConnection,
    );
    await verifyType(
      DioExceptionType.badCertificate,
      RecognitionFailureType.badCertificate,
    );
  });
}

AudioHandoff _handoff(String path) => AudioHandoff(
      path: path,
      duration: const Duration(seconds: 2),
      sizeBytes: 64044,
    );

Map<String, dynamic> _response() => <String, dynamic>{
      'id': 'recognition-id',
      'recognized_number': 42,
      'zarma_text': 'waranka cindi hinka',
      'normalized_text': 'waranka cindi hinka',
      'confidence': 0.95,
      'decision': 'accept',
      'alternatives': <dynamic>[],
      'model_version': 'mock-1',
      'grammar_version': 'v1',
      'latency_total_ms': 50,
      'latency_asr_ms': 40,
    };
