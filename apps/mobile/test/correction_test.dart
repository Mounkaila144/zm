import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:zarma_mobile/config/anon_id.dart';
import 'package:zarma_mobile/correction/zarma_generator_repository.dart';
import 'package:zarma_mobile/feedback/feedback_models.dart';
import 'package:zarma_mobile/feedback/feedback_repository.dart';
import 'package:zarma_mobile/models/recognition_result.dart';
import 'package:zarma_mobile/navigation/app_routes.dart';
import 'package:zarma_mobile/widgets/number_keypad.dart';
import 'package:zarma_mobile/widgets/zarma_number_display.dart';

class FakeGeneratorRepository implements ZarmaGeneratorRepository {
  FakeGeneratorRepository(this.handler);

  final Future<ZarmaGeneration> Function(int number) handler;
  final List<int> calls = <int>[];

  @override
  Future<ZarmaGeneration> generate({
    required int number,
    required CancelToken cancelToken,
  }) {
    calls.add(number);
    return handler(number);
  }
}

class RecordingFeedbackRepository implements FeedbackRepository {
  RecordingFeedbackRepository(this.handler);

  final Future<FeedbackResponse> Function(FeedbackRequest request) handler;
  final List<FeedbackRequest> requests = <FeedbackRequest>[];

  @override
  Future<FeedbackResponse> submit({
    required FeedbackRequest request,
    required String expectedModelVersion,
    required String expectedGrammarVersion,
    required CancelToken cancelToken,
  }) {
    requests.add(request);
    return handler(request);
  }
}

class MockGeneratorRepository extends Mock
    implements ZarmaGeneratorRepository {}

class MockFeedbackRepository extends Mock implements FeedbackRepository {}

class FakeFeedbackRequest extends Fake implements FeedbackRequest {}

const String _zarma235 = 'zangou hinka nda waranza cindi gou';

void main() {
  setUpAll(() {
    registerFallbackValue(CancelToken());
    registerFallbackValue(FakeFeedbackRequest());
  });

  testWidgets('saisie 235 affiche la forme zarma générée par l’API',
      (WidgetTester tester) async {
    final FakeGeneratorRepository generator = FakeGeneratorRepository(
      (int n) async => ZarmaGeneration(
        number: n,
        zarmaText: _zarma235,
        grammarVersion: '1.1.0',
      ),
    );

    await _pumpCorrection(tester, generator: generator);
    await tester.enterText(find.byType(NumberKeypad), '235');
    await tester.pump(); // onChanged → chargement
    await tester.pump(const Duration(milliseconds: 350)); // debounce → generate
    await tester.pump(); // microtask repo
    await tester.pump(); // rebuild data

    expect(generator.calls, <int>[235]);
    expect(find.text(_zarma235), findsOneWidget);
    expect(
      find.descendant(
        of: find.byType(ZarmaNumberDisplay),
        matching: find.text('235'),
      ),
      findsOneWidget,
    );
  });

  testWidgets('un nombre hors plage est refusé sans appel API ni envoi',
      (WidgetTester tester) async {
    final FakeGeneratorRepository generator = FakeGeneratorRepository(
      (int n) async => ZarmaGeneration(
        number: n,
        zarmaText: 'x',
        grammarVersion: '1.1.0',
      ),
    );

    await _pumpCorrection(tester, generator: generator);
    await tester.enterText(find.byType(NumberKeypad), '2000000');
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 350));

    expect(generator.calls, isEmpty);
    expect(find.byKey(const Key('correction-range-error')), findsOneWidget);
    final FilledButton submit = tester.widget(
      find.byKey(const Key('submit-correction-button')),
    );
    expect(submit.onPressed, isNull);
  });

  testWidgets('une correction valide envoie un feedback corrected',
      (WidgetTester tester) async {
    final FakeGeneratorRepository generator = FakeGeneratorRepository(
      (int n) async => ZarmaGeneration(
        number: n,
        zarmaText: _zarma235,
        grammarVersion: '1.1.0',
      ),
    );
    final RecordingFeedbackRepository feedback = RecordingFeedbackRepository(
      (FeedbackRequest r) async => _receiptFor(r),
    );

    await _pumpCorrection(tester, generator: generator, feedback: feedback);
    await tester.enterText(find.byType(NumberKeypad), '235');
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 350));
    await tester.pump();
    await tester.pump();

    await tester.tap(find.byKey(const Key('submit-correction-button')));
    await tester.pumpAndSettle();

    expect(feedback.requests, hasLength(1));
    final FeedbackRequest request = feedback.requests.single;
    expect(request.feedbackType, FeedbackType.corrected);
    expect(request.proposedNumber, 42);
    expect(request.correctedNumber, 235);
    expect(request.recognitionId, 'rec-id');
    expect(find.byKey(const Key('result-screen')), findsOneWidget);
    expect(find.text('235'), findsOneWidget);
    expect(find.text(_zarma235), findsOneWidget);
  });

  testWidgets('une erreur de génération API affiche un message clair',
      (WidgetTester tester) async {
    final FakeGeneratorRepository generator = FakeGeneratorRepository(
      (int n) async => throw const GenerationFailure(
        type: GenerationFailureType.unavailable,
        message: 'Ce nombre n’a pas encore de forme zarma disponible.',
      ),
    );

    await _pumpCorrection(tester, generator: generator);
    await tester.enterText(find.byType(NumberKeypad), '500');
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 350));
    await tester.pump();
    await tester.pump();

    expect(
      find.text('Ce nombre n’a pas encore de forme zarma disponible.'),
      findsOneWidget,
    );
    final FilledButton submit = tester.widget(
      find.byKey(const Key('submit-correction-button')),
    );
    expect(submit.onPressed, isNull);
  });

  testWidgets('un double tap ne soumet qu’un seul feedback', (
    WidgetTester tester,
  ) async {
    final MockGeneratorRepository generator = MockGeneratorRepository();
    final MockFeedbackRepository feedback = MockFeedbackRepository();
    final Completer<FeedbackResponse> pending = Completer<FeedbackResponse>();
    when(
      () => generator.generate(
        number: any(named: 'number'),
        cancelToken: any(named: 'cancelToken'),
      ),
    ).thenAnswer(
      (_) async => const ZarmaGeneration(
        number: 235,
        zarmaText: _zarma235,
        grammarVersion: '1.1.0',
      ),
    );
    when(
      () => feedback.submit(
        request: any(named: 'request'),
        expectedModelVersion: any(named: 'expectedModelVersion'),
        expectedGrammarVersion: any(named: 'expectedGrammarVersion'),
        cancelToken: any(named: 'cancelToken'),
      ),
    ).thenAnswer((_) => pending.future);

    await _pumpCorrection(tester, generator: generator, feedback: feedback);
    await tester.enterText(find.byType(NumberKeypad), '235');
    await tester.pump(const Duration(milliseconds: 350));
    await tester.pump();

    final Finder submit = find.byKey(const Key('submit-correction-button'));
    await tester.tap(submit);
    await tester.tap(submit);
    await tester.pump();

    verify(
      () => feedback.submit(
        request: any(named: 'request'),
        expectedModelVersion: 'mock',
        expectedGrammarVersion: 'v1',
        cancelToken: any(named: 'cancelToken'),
      ),
    ).called(1);

    pending.complete(_receiptFor(_correctedRequest()));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('result-screen')), findsOneWidget);
  });

  testWidgets('un échec de feedback affiche Réessayer puis réussit', (
    WidgetTester tester,
  ) async {
    final MockGeneratorRepository generator = MockGeneratorRepository();
    final MockFeedbackRepository feedback = MockFeedbackRepository();
    int attempts = 0;
    when(
      () => generator.generate(
        number: any(named: 'number'),
        cancelToken: any(named: 'cancelToken'),
      ),
    ).thenAnswer(
      (_) async => const ZarmaGeneration(
        number: 235,
        zarmaText: _zarma235,
        grammarVersion: '1.1.0',
      ),
    );
    when(
      () => feedback.submit(
        request: any(named: 'request'),
        expectedModelVersion: any(named: 'expectedModelVersion'),
        expectedGrammarVersion: any(named: 'expectedGrammarVersion'),
        cancelToken: any(named: 'cancelToken'),
      ),
    ).thenAnswer((Invocation invocation) async {
      attempts++;
      if (attempts == 1) {
        throw const FeedbackFailure(
          type: FeedbackFailureType.noConnection,
          message: 'Impossible d’envoyer le choix pour le moment.',
        );
      }
      final FeedbackRequest request =
          invocation.namedArguments[#request] as FeedbackRequest;
      return _receiptFor(request);
    });

    await _pumpCorrection(tester, generator: generator, feedback: feedback);
    await tester.enterText(find.byType(NumberKeypad), '235');
    await tester.pump(const Duration(milliseconds: 350));
    await tester.pump();
    await tester.tap(find.byKey(const Key('submit-correction-button')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('correction-feedback-error')), findsOneWidget);
    expect(find.byKey(const Key('correction-feedback-retry')), findsOneWidget);

    await tester.tap(find.byKey(const Key('correction-feedback-retry')));
    await tester.pumpAndSettle();
    expect(attempts, 2);
    expect(find.byKey(const Key('result-screen')), findsOneWidget);
  });
}

Future<void> _pumpCorrection(
  WidgetTester tester, {
  required ZarmaGeneratorRepository generator,
  FeedbackRepository? feedback,
}) async {
  final FeedbackRepository feedbackRepo = feedback ??
      RecordingFeedbackRepository((FeedbackRequest r) async => _receiptFor(r));
  await tester.pumpWidget(
    ProviderScope(
      overrides: <Override>[
        zarmaGeneratorRepositoryProvider.overrideWithValue(generator),
        feedbackRepositoryProvider.overrideWithValue(feedbackRepo),
        anonIdProvider.overrideWithValue('anon-id'),
      ],
      child: const MaterialApp(
        onGenerateRoute: AppRoutes.onGenerateRoute,
        home: Scaffold(key: Key('host-screen')),
      ),
    ),
  );
  final NavigatorState navigator = tester.state(find.byType(Navigator));
  navigator.pushNamed(AppRoutes.correction, arguments: _result());
  await tester.pumpAndSettle();
}

RecognitionResult _result() {
  return const RecognitionResult(
    id: 'rec-id',
    recognizedNumber: 42,
    zarmaText: 'waranka cindi hinka',
    normalizedText: 'waranka cindi hinka',
    confidence: 0.6,
    decision: Decision.confirm,
    modelVersion: 'mock',
    grammarVersion: 'v1',
  );
}

FeedbackResponse _receiptFor(FeedbackRequest request) {
  return FeedbackResponse(
    id: 'feedback-id',
    recognitionId: request.recognitionId,
    anonId: request.anonId,
    feedbackType: request.feedbackType,
    proposedNumber: request.proposedNumber,
    correctedNumber: request.correctedNumber,
    modelVersion: 'mock',
    grammarVersion: 'v1',
    createdAt: DateTime.utc(2026, 7, 24),
  );
}

FeedbackRequest _correctedRequest() {
  return const FeedbackRequest(
    recognitionId: 'rec-id',
    anonId: 'anon-id',
    feedbackType: FeedbackType.corrected,
    proposedNumber: 42,
    correctedNumber: 235,
  );
}
