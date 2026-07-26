import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:zarma_mobile/config/anon_id.dart';
import 'package:zarma_mobile/history/history_repository.dart';
import 'package:zarma_mobile/models/recognition_result.dart';
import 'package:zarma_mobile/navigation/app_routes.dart';
import 'package:zarma_mobile/network/api_client.dart';
import 'package:zarma_mobile/screens/history_screen.dart';

class _MockDio extends Mock implements Dio {}

/// Repository de test : contrôle finement l'état renvoyé au provider.
class _FakeHistoryRepository implements HistoryRepository {
  _FakeHistoryRepository(this._future);

  final Future<List<RecognitionResult>> _future;

  @override
  Future<List<RecognitionResult>> fetch({
    required String anonId,
    int limit = 50,
    CancelToken? cancelToken,
  }) =>
      _future;
}

class _ScriptedHistoryRepository implements HistoryRepository {
  _ScriptedHistoryRepository(this.responses);

  final List<Future<List<RecognitionResult>>> responses;
  int calls = 0;

  @override
  Future<List<RecognitionResult>> fetch({
    required String anonId,
    int limit = 50,
    CancelToken? cancelToken,
  }) {
    final int index = calls < responses.length ? calls : responses.length - 1;
    calls++;
    return responses[index];
  }
}

const String _anonId = '00000000-0000-4000-8000-0000000000aa';

Map<String, dynamic> _sampleJson({
  int number = 42,
  String zarma = 'waranka cindi hinka',
  String createdAt = '2026-07-24T10:15:00Z',
}) {
  return <String, dynamic>{
    'id': '11111111-1111-4111-8111-111111111111',
    'recognized_number': number,
    'zarma_text': zarma,
    'normalized_text': zarma,
    'confidence': 0.91,
    'decision': 'accept',
    'alternatives': <dynamic>[],
    'model_version': 'mock-1',
    'grammar_version': 'v1',
    'created_at': createdAt,
    'latency_total_ms': 120,
    'latency_asr_ms': 40,
  };
}

Widget _harness({required HistoryRepository repository}) {
  return ProviderScope(
    overrides: <Override>[
      anonIdProvider.overrideWithValue(_anonId),
      historyRepositoryProvider.overrideWithValue(repository),
    ],
    child: const MaterialApp(
      home: HistoryScreen(),
    ),
  );
}

void main() {
  group('RecognitionResult.fromJson', () {
    test('mappe les champs de la réponse /history', () {
      final RecognitionResult result =
          RecognitionResult.fromJson(_sampleJson());

      expect(result.recognizedNumber, 42);
      expect(result.zarmaText, 'waranka cindi hinka');
      expect(result.confidence, 0.91);
      expect(result.decision, Decision.accept);
      expect(result.createdAt, isNotNull);
    });

    test('tolère un nombre nul et une date absente', () {
      final RecognitionResult result = RecognitionResult.fromJson(
        <String, dynamic>{
          'id': 'x',
          'recognized_number': null,
          'zarma_text': '',
          'normalized_text': '',
          'confidence': 0.0,
          'decision': 'repeat',
          'model_version': 'm',
          'grammar_version': 'v1',
        },
      );

      expect(result.recognizedNumber, isNull);
      expect(result.decision, Decision.repeat);
      expect(result.createdAt, isNull);
    });
  });

  group('HistoryRepository.fetch (ApiClient mocké)', () {
    late _MockDio dio;
    late HistoryRepository repository;

    setUp(() {
      dio = _MockDio();
      repository = HistoryRepository(dio);
    });

    test('appelle /history avec anon_id + limit et mappe la liste', () async {
      when(() => dio.get<List<dynamic>>(
            any(),
            queryParameters: any(named: 'queryParameters'),
            cancelToken: any(named: 'cancelToken'),
          )).thenAnswer(
        (_) async => Response<List<dynamic>>(
          requestOptions: RequestOptions(path: '/history'),
          statusCode: 200,
          data: <dynamic>[_sampleJson()],
        ),
      );

      final List<RecognitionResult> results =
          await repository.fetch(anonId: _anonId, limit: 25);

      expect(results, hasLength(1));
      expect(results.first.recognizedNumber, 42);
      final Map<String, dynamic> captured = verify(
        () => dio.get<List<dynamic>>(
          '/history',
          queryParameters: captureAny(named: 'queryParameters'),
          cancelToken: any(named: 'cancelToken'),
        ),
      ).captured.single as Map<String, dynamic>;
      expect(captured['anon_id'], _anonId);
      expect(captured['limit'], 25);
    });

    test('normalise une erreur réseau en NetworkFailure', () async {
      when(() => dio.get<List<dynamic>>(
            any(),
            queryParameters: any(named: 'queryParameters'),
            cancelToken: any(named: 'cancelToken'),
          )).thenThrow(
        DioException(
          requestOptions: RequestOptions(path: '/history'),
          type: DioExceptionType.connectionError,
        ),
      );

      await expectLater(
        repository.fetch(anonId: _anonId),
        throwsA(isA<NetworkFailure>()),
      );
    });
  });

  group('HistoryScreen — états', () {
    testWidgets('chargement : affiche un indicateur',
        (WidgetTester tester) async {
      final Completer<List<RecognitionResult>> pending =
          Completer<List<RecognitionResult>>();
      await tester.pumpWidget(
        _harness(repository: _FakeHistoryRepository(pending.future)),
      );
      await tester.pump();

      expect(find.byKey(const Key('history-loading')), findsOneWidget);
      pending.complete(<RecognitionResult>[]);
      await tester.pumpAndSettle();
    });

    testWidgets('vide : affiche un message dédié', (WidgetTester tester) async {
      await tester.pumpWidget(
        _harness(
          repository: _FakeHistoryRepository(
            Future<List<RecognitionResult>>.value(<RecognitionResult>[]),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('history-empty')), findsOneWidget);
      expect(
          find.text('Aucune reconnaissance pour le moment.'), findsOneWidget);
    });

    testWidgets('erreur : message + bouton réessayer',
        (WidgetTester tester) async {
      final Completer<List<RecognitionResult>> pending =
          Completer<List<RecognitionResult>>();
      final _ScriptedHistoryRepository repository =
          _ScriptedHistoryRepository(
        <Future<List<RecognitionResult>>>[
          pending.future,
          Future<List<RecognitionResult>>.value(
            <RecognitionResult>[RecognitionResult.fromJson(_sampleJson())],
          ),
        ],
      );
      await tester.pumpWidget(
        _harness(repository: repository),
      );
      pending.completeError(
        const NetworkFailure(
          type: NetworkFailureType.noConnection,
          message: 'Impossible de joindre le serveur.',
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('history-error')), findsOneWidget);
      expect(find.text('Impossible de joindre le serveur.'), findsOneWidget);
      expect(find.byKey(const Key('history-retry')), findsOneWidget);

      await tester.tap(find.byKey(const Key('history-retry')));
      await tester.pumpAndSettle();

      expect(repository.calls, 2);
      expect(find.byKey(const Key('history-list')), findsOneWidget);
      expect(find.text('42'), findsOneWidget);
    });

    testWidgets('liste peuplée : nombre, forme zarma et date', (
      WidgetTester tester,
    ) async {
      final List<RecognitionResult> items = <RecognitionResult>[
        RecognitionResult.fromJson(_sampleJson()),
        RecognitionResult.fromJson(
          _sampleJson(
              number: 7, zarma: 'iyye', createdAt: '2026-07-23T08:00:00Z'),
        ),
      ];
      await tester.pumpWidget(
        _harness(
          repository: _FakeHistoryRepository(
            Future<List<RecognitionResult>>.value(items),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('history-list')), findsOneWidget);
      expect(find.text('42'), findsOneWidget);
      expect(find.text('waranka cindi hinka'), findsNothing);
      expect(find.text('7'), findsOneWidget);
      // La date est affichée pour chaque élément (année stable quel que soit
      // le fuseau du runner CI).
      expect(find.textContaining('2026'), findsNWidgets(2));
    });
  });

  testWidgets('la route /history reste enregistrée',
      (WidgetTester tester) async {
    expect(AppRoutes.routes.containsKey(AppRoutes.history), isTrue);
  });
}
