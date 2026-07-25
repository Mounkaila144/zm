import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:zarma_mobile/app.dart';
import 'package:zarma_mobile/config/anon_id.dart';
import 'package:zarma_mobile/features/contribution/data/consent_repository.dart';
import 'package:zarma_mobile/features/contribution/data/contribution_prompt_repository.dart';
import 'package:zarma_mobile/features/contribution/models/contribution_models.dart';
import 'package:zarma_mobile/navigation/app_routes.dart';

class _MockDio extends Mock implements Dio {}

class _FakeConsentRepository implements ConsentRepository {
  int fetchCalls = 0;
  int acceptCalls = 0;
  String? acceptedAnonId;
  String? acceptedVersion;

  @override
  Future<ConsentContent> fetchCurrent({
    required CancelToken cancelToken,
  }) async {
    fetchCalls++;
    return const ConsentContent(
      consentVersion: '1.0.0',
      text: 'Usage\nAnonymat\nConservation\nRetrait',
    );
  }

  @override
  Future<ConsentAcceptance> accept({
    required String anonId,
    required String consentVersion,
    required CancelToken cancelToken,
  }) async {
    acceptCalls++;
    acceptedAnonId = anonId;
    acceptedVersion = consentVersion;
    return ConsentAcceptance(
      id: '11111111-1111-4111-8111-111111111111',
      anonId: anonId,
      consentVersion: consentVersion,
      acceptedAt: DateTime.utc(2026, 7, 24),
      withdrawn: false,
    );
  }
}

class _FakePromptRepository implements ContributionPromptRepository {
  @override
  Future<ContributionPrompt> nextPrompt({
    required CancelToken cancelToken,
  }) async {
    return const ContributionPrompt(
      expectedNumber: 100,
      expectedPrompt: 'zangou',
      category: ContributionPromptCategory.asrConfusion,
      grammarVersion: '1.1.0',
    );
  }
}

const String _anonId = '00000000-0000-4000-8000-000000000041';

void main() {
  group('DioConsentRepository', () {
    late _MockDio dio;
    late DioConsentRepository repository;

    setUp(() {
      dio = _MockDio();
      repository = DioConsentRepository(dio);
    });

    test('GET /consent retourne le texte et sa version', () async {
      when(
        () => dio.get<dynamic>(
          '/consent',
          cancelToken: any(named: 'cancelToken'),
        ),
      ).thenAnswer(
        (_) async => Response<dynamic>(
          requestOptions: RequestOptions(path: '/consent'),
          statusCode: 200,
          data: <String, dynamic>{
            'consent_version': '1.0.0',
            'text': 'Usage Anonymat Conservation Retrait',
          },
        ),
      );

      final ConsentContent content = await repository.fetchCurrent(
        cancelToken: CancelToken(),
      );

      expect(content.consentVersion, '1.0.0');
      expect(content.text, contains('Retrait'));
      verify(
        () => dio.get<dynamic>(
          '/consent',
          cancelToken: any(named: 'cancelToken'),
        ),
      ).called(1);
    });

    test('Accepter déclenche POST /consent avec anon_id et version', () async {
      when(
        () => dio.post<dynamic>(
          '/consent',
          data: any(named: 'data'),
          cancelToken: any(named: 'cancelToken'),
        ),
      ).thenAnswer(
        (_) async => Response<dynamic>(
          requestOptions: RequestOptions(path: '/consent'),
          statusCode: 201,
          data: <String, dynamic>{
            'id': '11111111-1111-4111-8111-111111111111',
            'anon_id': _anonId,
            'consent_version': '1.0.0',
            'accepted_at': '2026-07-24T10:00:00Z',
            'withdrawn': false,
          },
        ),
      );

      await repository.accept(
        anonId: _anonId,
        consentVersion: '1.0.0',
        cancelToken: CancelToken(),
      );

      final Map<String, dynamic> body = verify(
        () => dio.post<dynamic>(
          '/consent',
          data: captureAny(named: 'data'),
          cancelToken: any(named: 'cancelToken'),
        ),
      ).captured.single as Map<String, dynamic>;
      expect(body['anon_id'], _anonId);
      expect(body['consent_version'], '1.0.0');
    });
  });

  testWidgets(
    'la garde bloque /contribute puis Accepter ouvre le flux protégé',
    (WidgetTester tester) async {
      final _FakeConsentRepository repository = _FakeConsentRepository();
      await tester.pumpWidget(
        ProviderScope(
          overrides: <Override>[
            anonIdProvider.overrideWithValue(_anonId),
            consentRepositoryProvider.overrideWithValue(repository),
            contributionPromptRepositoryProvider.overrideWithValue(
              _FakePromptRepository(),
            ),
          ],
          child: const ZarmaApp(),
        ),
      );

      await tester.tap(find.byKey(const Key('open-contribution-button')));
      await tester.pumpAndSettle();

      expect(AppRoutes.routes.containsKey(AppRoutes.contribute), isTrue);
      expect(find.byKey(const Key('consent-screen')), findsOneWidget);
      expect(find.byKey(const Key('contribution-screen')), findsNothing);
      expect(
          find.text('Usage\nAnonymat\nConservation\nRetrait'), findsOneWidget);
      expect(find.text('Version 1.0.0'), findsOneWidget);

      await tester.tap(find.byKey(const Key('accept-consent-button')));
      await tester.pumpAndSettle();

      expect(repository.acceptCalls, 1);
      expect(repository.acceptedAnonId, _anonId);
      expect(repository.acceptedVersion, '1.0.0');
      expect(find.byKey(const Key('consent-screen')), findsNothing);
      expect(find.byKey(const Key('contribution-screen')), findsOneWidget);
      expect(find.text('zangou'), findsOneWidget);
    },
  );
}
