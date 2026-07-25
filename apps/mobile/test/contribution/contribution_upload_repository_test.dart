import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:zarma_mobile/features/contribution/data/contribution_upload_repository.dart';
import 'package:zarma_mobile/features/contribution/models/contribution_models.dart';
import 'package:zarma_mobile/recording/audio_recording_models.dart';

class _MockDio extends Mock implements Dio {}

void main() {
  late _MockDio dio;
  late DioContributionUploadRepository repository;
  late Directory directory;
  late File audioFile;

  setUp(() async {
    dio = _MockDio();
    repository = DioContributionUploadRepository(dio);
    directory = await Directory.systemTemp.createTemp('contribution_upload_');
    audioFile = File('${directory.path}/private-device-take.wav');
    await audioFile.writeAsBytes(<int>[82, 73, 70, 70]);
  });

  tearDown(() async {
    await directory.delete(recursive: true);
  });

  test('poste un multipart WAV exact sans base64 ni champ local sensible',
      () async {
    when(
      () => dio.post<dynamic>(
        any(),
        data: any(named: 'data'),
        cancelToken: any(named: 'cancelToken'),
      ),
    ).thenAnswer(
      (_) async => Response<dynamic>(
        requestOptions: RequestOptions(path: '/recordings'),
        statusCode: 201,
        data: _receiptJson(),
      ),
    );
    final CancelToken token = CancelToken();

    final ContributionReceipt receipt = await repository.upload(
      contribution: _pending(audioFile.path),
      cancelToken: token,
    );

    expect(receipt.id, '22222222-2222-4222-8222-222222222222');
    expect(receipt.status, 'pending');
    final List<dynamic> captured = verify(
      () => dio.post<dynamic>(
        '/recordings',
        data: captureAny(named: 'data'),
        cancelToken: captureAny(named: 'cancelToken'),
      ),
    ).captured;
    final FormData body = captured[0] as FormData;
    expect(
      Map<String, String>.fromEntries(body.fields),
      <String, String>{
        'consent_id': '11111111-1111-4111-8111-111111111111',
        'anon_id': '00000000-0000-4000-8000-000000000042',
        'expected_number': '42',
        'expected_prompt': 'waranka cindi hinka',
        'grammar_version': '1.1.0',
        'region': 'Niamey',
        'device_info': 'android',
      },
    );
    expect(body.fields.map((e) => e.key), isNot(contains('consent_version')));
    expect(body.files, hasLength(1));
    expect(body.files.single.key, 'audio');
    expect(body.files.single.value.filename, 'contribution.wav');
    expect(body.files.single.value.contentType.toString(), 'audio/wav');
    expect(captured[1], same(token));
    expect(body.toString(), isNot(contains(audioFile.path)));
    expect(body.toString().toLowerCase(), isNot(contains('base64')));
  });

  test('omet proprement les métadonnées optionnelles nulles', () async {
    when(
      () => dio.post<dynamic>(
        any(),
        data: any(named: 'data'),
        cancelToken: any(named: 'cancelToken'),
      ),
    ).thenAnswer(
      (_) async => Response<dynamic>(
        requestOptions: RequestOptions(path: '/recordings'),
        statusCode: 201,
        data: _receiptJson(),
      ),
    );

    await repository.upload(
      contribution: _pending(audioFile.path, optionalMetadata: false),
      cancelToken: CancelToken(),
    );

    final FormData body = verify(
      () => dio.post<dynamic>(
        '/recordings',
        data: captureAny(named: 'data'),
        cancelToken: any(named: 'cancelToken'),
      ),
    ).captured.single as FormData;
    expect(body.fields.map((e) => e.key), isNot(contains('region')));
    expect(body.fields.map((e) => e.key), isNot(contains('device_info')));
  });

  test('rejette un reçu incomplet ou incohérent', () async {
    Future<void> expectInvalid(Map<String, dynamic> response) async {
      reset(dio);
      when(
        () => dio.post<dynamic>(
          any(),
          data: any(named: 'data'),
          cancelToken: any(named: 'cancelToken'),
        ),
      ).thenAnswer(
        (_) async => Response<dynamic>(
          requestOptions: RequestOptions(path: '/recordings'),
          statusCode: 201,
          data: response,
        ),
      );
      await expectLater(
        repository.upload(
          contribution: _pending(audioFile.path),
          cancelToken: CancelToken(),
        ),
        throwsA(
          isA<ContributionUploadFailure>().having(
            (e) => e.type,
            'type',
            ContributionUploadFailureType.invalidResponse,
          ),
        ),
      );
    }

    await expectInvalid(<String, dynamic>{'status': 'pending'});
    await expectInvalid(<String, dynamic>{
      ..._receiptJson(),
      'expected_number': 99,
    });
    await expectInvalid(<String, dynamic>{
      ..._receiptJson(),
      'status': 'validated',
    });
  });

  final Map<int, ContributionUploadFailureType> statusMappings =
      <int, ContributionUploadFailureType>{
    403: ContributionUploadFailureType.invalidConsent,
    413: ContributionUploadFailureType.invalidContribution,
    422: ContributionUploadFailureType.invalidContribution,
    429: ContributionUploadFailureType.rateLimited,
    500: ContributionUploadFailureType.serviceUnavailable,
    503: ContributionUploadFailureType.serviceUnavailable,
  };
  for (final MapEntry<int, ContributionUploadFailureType> mapping
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
          requestOptions: RequestOptions(path: '/recordings'),
          response: Response<dynamic>(
            requestOptions: RequestOptions(path: '/recordings'),
            statusCode: mapping.key,
            data: <String, dynamic>{
              'error': <String, dynamic>{
                'code': mapping.key == 403
                    ? 'CONSENT_INVALID'
                    : 'SERVER_PRIVATE_DETAIL',
                'message': 'backend secret',
                'request_id': 'request-123',
              },
            },
          ),
        ),
      );

      await expectLater(
        repository.upload(
          contribution: _pending(audioFile.path),
          cancelToken: CancelToken(),
        ),
        throwsA(
          isA<ContributionUploadFailure>()
              .having((e) => e.type, 'type', mapping.value)
              .having((e) => e.requestId, 'requestId', 'request-123')
              .having((e) => e.message, 'message', isNot(contains('secret'))),
        ),
      );
    });
  }

  final Map<DioExceptionType, ContributionUploadFailureType> networkMappings =
      <DioExceptionType, ContributionUploadFailureType>{
    DioExceptionType.receiveTimeout: ContributionUploadFailureType.timeout,
    DioExceptionType.connectionError:
        ContributionUploadFailureType.noConnection,
    DioExceptionType.badCertificate:
        ContributionUploadFailureType.badCertificate,
    DioExceptionType.cancel: ContributionUploadFailureType.cancelled,
  };
  for (final MapEntry<DioExceptionType, ContributionUploadFailureType> mapping
      in networkMappings.entries) {
    test('mappe ${mapping.key.name} vers ${mapping.value.name}', () async {
      when(
        () => dio.post<dynamic>(
          any(),
          data: any(named: 'data'),
          cancelToken: any(named: 'cancelToken'),
        ),
      ).thenThrow(
        DioException(
          requestOptions: RequestOptions(path: '/recordings'),
          type: mapping.key,
        ),
      );

      await expectLater(
        repository.upload(
          contribution: _pending(audioFile.path),
          cancelToken: CancelToken(),
        ),
        throwsA(
          isA<ContributionUploadFailure>().having(
            (e) => e.type,
            'type',
            mapping.value,
          ),
        ),
      );
    });
  }
}

PendingContribution _pending(
  String path, {
  bool optionalMetadata = true,
}) {
  return PendingContribution(
    audio: AudioHandoff(
      path: path,
      duration: const Duration(seconds: 2),
      sizeBytes: 64044,
    ),
    expectedNumber: 42,
    expectedPrompt: 'waranka cindi hinka',
    anonId: '00000000-0000-4000-8000-000000000042',
    consentId: '11111111-1111-4111-8111-111111111111',
    grammarVersion: '1.1.0',
    consentVersion: '1.0.0',
    region: optionalMetadata ? 'Niamey' : null,
    deviceInfo: optionalMetadata ? 'android' : null,
  );
}

Map<String, dynamic> _receiptJson() => <String, dynamic>{
      'id': '22222222-2222-4222-8222-222222222222',
      'status': 'pending',
      'expected_number': 42,
      'expected_prompt': 'waranka cindi hinka',
      'model_version': 'mock-1',
      'grammar_version': '1.1.0',
      'created_at': '2026-07-24T12:00:00Z',
    };
