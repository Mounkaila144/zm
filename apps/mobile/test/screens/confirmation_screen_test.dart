import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:zarma_mobile/config/anon_id.dart';
import 'package:zarma_mobile/feedback/feedback_models.dart';
import 'package:zarma_mobile/feedback/feedback_repository.dart';
import 'package:zarma_mobile/models/recognition_result.dart';
import 'package:zarma_mobile/navigation/app_routes.dart';

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

void main() {
  testWidgets('confirm ordonne et déduplique proposition et alternatives',
      (WidgetTester tester) async {
    final RecordingFeedbackRepository repository =
        RecordingFeedbackRepository((FeedbackRequest r) async => _receiptFor(r));

    await _pumpConfirmation(tester, _confirmResult(), repository);

    expect(find.byKey(const Key('candidate-option-42')), findsOneWidget);
    expect(find.byKey(const Key('candidate-option-7')), findsOneWidget);
    // Le doublon 42 et l'alternative sans nombre ne sont pas affichés.
    expect(find.text('42'), findsOneWidget);
    expect(find.byKey(const Key('repeat-message')), findsNothing);
  });

  testWidgets('sélection de la proposition principale envoie confirmed',
      (WidgetTester tester) async {
    final RecordingFeedbackRepository repository =
        RecordingFeedbackRepository((FeedbackRequest r) async => _receiptFor(r));

    await _pumpConfirmation(tester, _confirmResult(), repository);
    await tester.tap(find.byKey(const Key('candidate-option-42')));
    await tester.pumpAndSettle();

    expect(repository.requests, hasLength(1));
    expect(repository.requests.single.feedbackType, FeedbackType.confirmed);
    expect(repository.requests.single.proposedNumber, 42);
    expect(repository.requests.single.correctedNumber, isNull);
    expect(find.byKey(const Key('result-screen')), findsOneWidget);
    expect(find.text('42'), findsOneWidget);
  });

  testWidgets('sélection d’une alternative confirme ce nombre',
      (WidgetTester tester) async {
    final RecordingFeedbackRepository repository =
        RecordingFeedbackRepository((FeedbackRequest r) async => _receiptFor(r));

    await _pumpConfirmation(tester, _confirmResult(), repository);
    await tester.tap(find.byKey(const Key('candidate-option-7')));
    await tester.pumpAndSettle();

    expect(repository.requests.single.feedbackType, FeedbackType.confirmed);
    expect(repository.requests.single.proposedNumber, 7);
    expect(find.byKey(const Key('result-screen')), findsOneWidget);
    expect(find.text('7'), findsOneWidget);
    expect(find.text('iyye'), findsOneWidget);
  });

  testWidgets('Répéter depuis confirm envoie repeat_requested',
      (WidgetTester tester) async {
    final RecordingFeedbackRepository repository =
        RecordingFeedbackRepository((FeedbackRequest r) async => _receiptFor(r));

    await _pumpConfirmation(tester, _confirmResult(), repository);
    await tester.tap(find.byKey(const Key('request-repeat-button')));
    await tester.pumpAndSettle();

    expect(
      repository.requests.single.feedbackType,
      FeedbackType.repeatRequested,
    );
    expect(repository.requests.single.proposedNumber, 42);
    expect(find.byKey(const Key('recording-screen')), findsOneWidget);
  });

  testWidgets('Corriger ouvre la route sans envoyer de feedback',
      (WidgetTester tester) async {
    final RecordingFeedbackRepository repository =
        RecordingFeedbackRepository((FeedbackRequest r) async => _receiptFor(r));

    await _pumpConfirmation(tester, _confirmResult(), repository);
    await tester.tap(find.byKey(const Key('open-correction-button')));
    await tester.pumpAndSettle();

    expect(repository.requests, isEmpty);
    expect(find.byKey(const Key('correction-screen')), findsOneWidget);
  });

  testWidgets('repeat n’affiche aucun candidat et invite à réenregistrer',
      (WidgetTester tester) async {
    final RecordingFeedbackRepository repository =
        RecordingFeedbackRepository((FeedbackRequest r) async => _receiptFor(r));

    await _pumpConfirmation(tester, _repeatResult(), repository);

    expect(find.byKey(const Key('repeat-message')), findsOneWidget);
    expect(find.byKey(const Key('candidate-option-42')), findsNothing);
    expect(find.textContaining('42'), findsNothing);

    await tester.tap(find.byKey(const Key('record-again-button')));
    await tester.pumpAndSettle();

    expect(
      repository.requests.single.feedbackType,
      FeedbackType.repeatRequested,
    );
    expect(repository.requests.single.proposedNumber, isNull);
    expect(find.byKey(const Key('recording-screen')), findsOneWidget);
  });

  testWidgets('un confirm sans candidat exploitable bascule en répétition',
      (WidgetTester tester) async {
    final RecordingFeedbackRepository repository =
        RecordingFeedbackRepository((FeedbackRequest r) async => _receiptFor(r));

    await _pumpConfirmation(tester, _confirmWithoutCandidate(), repository);

    expect(find.byKey(const Key('repeat-message')), findsOneWidget);
    expect(find.byKey(const Key('request-repeat-button')), findsNothing);
  });

  testWidgets('un échec affiche une erreur sûre et permet un retry',
      (WidgetTester tester) async {
    int calls = 0;
    final RecordingFeedbackRepository repository =
        RecordingFeedbackRepository((FeedbackRequest r) {
      calls++;
      if (calls == 1) {
        throw const FeedbackFailure(
          type: FeedbackFailureType.serviceUnavailable,
          message: 'Le service est momentanément indisponible.',
        );
      }
      return Future<FeedbackResponse>.value(_receiptFor(r));
    });

    await _pumpConfirmation(tester, _confirmResult(), repository);
    await tester.tap(find.byKey(const Key('candidate-option-42')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('feedback-error-message')), findsOneWidget);
    expect(find.byKey(const Key('confirmation-screen')), findsOneWidget);

    await tester.tap(find.byKey(const Key('feedback-retry-button')));
    await tester.pumpAndSettle();

    expect(calls, 2);
    expect(find.byKey(const Key('result-screen')), findsOneWidget);
  });

  testWidgets('un double tap ne déclenche qu’un seul envoi',
      (WidgetTester tester) async {
    final Completer<FeedbackResponse> pending = Completer<FeedbackResponse>();
    final RecordingFeedbackRepository repository =
        RecordingFeedbackRepository((FeedbackRequest r) => pending.future);

    await _pumpConfirmation(tester, _confirmResult(), repository);
    await tester.tap(find.byKey(const Key('candidate-option-42')));
    await tester.pump();
    await tester.tap(
      find.byKey(const Key('candidate-option-42')),
      warnIfMissed: false,
    );
    await tester.pump();

    expect(repository.requests, hasLength(1));
    expect(find.byKey(const Key('feedback-progress-indicator')), findsOneWidget);

    pending.complete(_receiptFor(repository.requests.single));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('result-screen')), findsOneWidget);
  });
}

Future<void> _pumpConfirmation(
  WidgetTester tester,
  RecognitionResult result,
  FeedbackRepository repository,
) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: <Override>[
        feedbackRepositoryProvider.overrideWithValue(repository),
        anonIdProvider.overrideWithValue('anon-id'),
      ],
      child: MaterialApp(
        onGenerateRoute: AppRoutes.onGenerateRoute,
        initialRoute: AppRoutes.recording,
        routes: <String, WidgetBuilder>{
          AppRoutes.recording: (_) => const Scaffold(
                key: Key('recording-screen'),
              ),
        },
      ),
    ),
  );
  final NavigatorState navigator = tester.state(find.byType(Navigator));
  navigator.pushNamed(AppRoutes.confirmation, arguments: result);
  await tester.pumpAndSettle();
}

RecognitionResult _confirmResult() {
  return const RecognitionResult(
    id: 'rec-id',
    recognizedNumber: 42,
    zarmaText: 'waranka cindi hinka',
    normalizedText: 'waranka cindi hinka',
    confidence: 0.6,
    decision: Decision.confirm,
    alternatives: <RecognitionAlternative>[
      RecognitionAlternative(
        number: 42,
        zarmaText: 'waranka cindi hinka',
        score: 0.55,
      ),
      RecognitionAlternative(number: 7, zarmaText: 'iyye', score: 0.4),
      RecognitionAlternative(number: null, zarmaText: 'bruit', score: 0.1),
    ],
    modelVersion: 'mock',
    grammarVersion: 'v1',
  );
}

RecognitionResult _repeatResult() {
  return const RecognitionResult(
    id: 'rec-id',
    recognizedNumber: null,
    zarmaText: '',
    normalizedText: '',
    confidence: 0.1,
    decision: Decision.repeat,
    modelVersion: 'mock',
    grammarVersion: 'v1',
  );
}

RecognitionResult _confirmWithoutCandidate() {
  return const RecognitionResult(
    id: 'rec-id',
    recognizedNumber: null,
    zarmaText: '',
    normalizedText: '',
    confidence: 0.5,
    decision: Decision.confirm,
    alternatives: <RecognitionAlternative>[
      RecognitionAlternative(number: null, zarmaText: 'bruit', score: 0.2),
    ],
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
