import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:zarma_mobile/correction/zarma_generator_repository.dart';

class MockDio extends Mock implements Dio {}

void main() {
  late MockDio dio;
  late DioZarmaGeneratorRepository repository;

  setUp(() {
    dio = MockDio();
    repository = DioZarmaGeneratorRepository(dio);
  });

  test('appelle le générateur API et valide son contrat versionné', () async {
    when(
      () => dio.get<dynamic>(
        any(),
        cancelToken: any(named: 'cancelToken'),
      ),
    ).thenAnswer(
      (_) async => Response<dynamic>(
        requestOptions: RequestOptions(path: '/grammar/generate/235'),
        statusCode: 200,
        data: <String, dynamic>{
          'number': 235,
          'zarma_text': 'zangou hinka nda waranza cindi gou',
          'grammar_version': '1.1.0',
        },
      ),
    );
    final CancelToken token = CancelToken();

    final ZarmaGeneration result = await repository.generate(
      number: 235,
      cancelToken: token,
    );

    expect(result.number, 235);
    expect(result.grammarVersion, '1.1.0');
    final List<dynamic> captured = verify(
      () => dio.get<dynamic>(
        '/grammar/generate/235',
        cancelToken: captureAny(named: 'cancelToken'),
      ),
    ).captured;
    expect(captured.single, same(token));
  });

  test('normalise un hors-plage sans exposer le message backend', () async {
    when(
      () => dio.get<dynamic>(
        any(),
        cancelToken: any(named: 'cancelToken'),
      ),
    ).thenThrow(
      DioException.badResponse(
        statusCode: 400,
        requestOptions: RequestOptions(path: '/grammar/generate/1000001'),
        response: Response<dynamic>(
          requestOptions: RequestOptions(path: '/grammar/generate/1000001'),
          statusCode: 400,
          data: <String, dynamic>{
            'error': <String, dynamic>{
              'code': 'OUT_OF_RANGE',
              'message': 'détail backend confidentiel',
              'request_id': 'request-1',
            },
          },
        ),
      ),
    );

    await expectLater(
      repository.generate(number: 1000001, cancelToken: CancelToken()),
      throwsA(
        isA<GenerationFailure>()
            .having(
              (GenerationFailure error) => error.type,
              'type',
              GenerationFailureType.outOfRange,
            )
            .having(
              (GenerationFailure error) => error.message,
              'message',
              isNot(contains('confidentiel')),
            ),
      ),
    );
  });

  test('rejette une réponse mal formée ou portant un autre nombre', () async {
    when(
      () => dio.get<dynamic>(
        any(),
        cancelToken: any(named: 'cancelToken'),
      ),
    ).thenAnswer(
      (_) async => Response<dynamic>(
        requestOptions: RequestOptions(path: '/grammar/generate/235'),
        statusCode: 200,
        data: <String, dynamic>{
          'number': 42,
          'zarma_text': 'forme incohérente',
          'grammar_version': '1.1.0',
        },
      ),
    );

    await expectLater(
      repository.generate(number: 235, cancelToken: CancelToken()),
      throwsA(
        isA<GenerationFailure>().having(
          (GenerationFailure error) => error.type,
          'type',
          GenerationFailureType.invalidResponse,
        ),
      ),
    );
  });
}
