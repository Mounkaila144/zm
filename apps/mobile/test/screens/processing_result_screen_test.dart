import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:zarma_mobile/models/recognition_result.dart';
import 'package:zarma_mobile/navigation/app_routes.dart';
import 'package:zarma_mobile/recognition/recognition_controller.dart';
import 'package:zarma_mobile/recognition/recognition_repository.dart';
import 'package:zarma_mobile/recording/audio_recording_models.dart';
import 'package:zarma_mobile/screens/processing_screen.dart';
import 'package:zarma_mobile/screens/result_screen.dart';

class WidgetRepository implements RecognitionRepository {
  WidgetRepository(this.handler);

  final Future<RecognitionResult> Function(CancelToken token) handler;

  @override
  Future<RecognitionResult> recognize({
    required AudioHandoff handoff,
    required String anonId,
    required CancelToken cancelToken,
  }) =>
      handler(cancelToken);
}

void main() {
  testWidgets('affiche immédiatement spinner, texte et Annuler',
      (tester) async {
    final Completer<RecognitionResult> pending = Completer<RecognitionResult>();
    final RecognitionController controller = _controller(
      WidgetRepository((_) => pending.future),
    );

    await _pumpProcessing(tester, controller);

    expect(
      find.byKey(const Key('recognition-progress-indicator')),
      findsOneWidget,
    );
    expect(find.textContaining('écoutons'), findsOneWidget);
    expect(find.byKey(const Key('cancel-recognition-button')), findsOneWidget);
    pending.completeError(
      const RecognitionFailure(
        type: RecognitionFailureType.cancelled,
        message: '',
      ),
    );
    await tester.pump();
  });

  testWidgets('affiche une erreur sûre et exige un réenregistrement', (
    tester,
  ) async {
    final RecognitionController controller = _controller(
      WidgetRepository(
        (_) async => throw const RecognitionFailure(
          type: RecognitionFailureType.timeout,
          message: 'Le traitement a pris trop de temps.',
        ),
      ),
    );

    await _pumpProcessing(tester, controller);
    await tester.pumpAndSettle();

    expect(find.text('Le traitement a pris trop de temps.'), findsOneWidget);
    expect(find.byKey(const Key('record-again-button')), findsOneWidget);
    expect(find.textContaining('Renvoyer'), findsNothing);
  });

  for (final Decision decision in Decision.values) {
    testWidgets('route ${decision.name} selon la décision serveur', (
      tester,
    ) async {
      final RecognitionController controller = _controller(
        WidgetRepository((_) async => _result(decision)),
      );

      await _pumpProcessing(tester, controller);
      await tester.pumpAndSettle();

      if (decision == Decision.accept) {
        expect(find.byKey(const Key('result-screen')), findsOneWidget);
      } else {
        expect(find.byKey(const Key('confirmation-screen')), findsOneWidget);
        expect(find.byKey(const Key('result-screen')), findsNothing);
      }
    });
  }

  testWidgets('Résultat affiche chiffres + zarma sans métadonnées', (
    tester,
  ) async {
    final RecognitionResult result = _result(Decision.accept);

    await tester.pumpWidget(
      MaterialApp(
        routes: _routesWithoutHome(),
        home: ResultScreen(result: result),
      ),
    );

    expect(find.text('42'), findsOneWidget);
    expect(find.text('waranka cindi hinka'), findsOneWidget);
    expect(find.textContaining('0.95'), findsNothing);
    expect(find.textContaining('mock'), findsNothing);
    expect(find.byKey(const Key('record-new-number-button')), findsOneWidget);
    expect(find.byKey(const Key('open-correction-button')), findsOneWidget);
  });
}

Future<void> _pumpProcessing(
  WidgetTester tester,
  RecognitionController controller,
) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: <Override>[
        recognitionControllerProvider.overrideWith(
          (ref, AudioHandoff handoff) => controller,
        ),
      ],
      child: MaterialApp(
        routes: _routesWithoutHome(),
        onGenerateRoute: AppRoutes.onGenerateRoute,
        home: const ProcessingScreen(handoff: _handoff),
      ),
    ),
  );
  await tester.pump();
  await tester.pump();
}

Map<String, WidgetBuilder> _routesWithoutHome() {
  return Map<String, WidgetBuilder>.from(AppRoutes.routes)
    ..remove(AppRoutes.home);
}

RecognitionController _controller(RecognitionRepository repository) {
  return RecognitionController(
    repository: repository,
    handoff: _handoff,
    anonId: 'anon',
    cancelTokenFactory: CancelToken.new,
    cleanup: () async {},
  );
}

const AudioHandoff _handoff = AudioHandoff(
  path: '/tmp/take.wav',
  duration: Duration(seconds: 2),
  sizeBytes: 64044,
);

RecognitionResult _result(Decision decision) => RecognitionResult(
      id: 'id',
      recognizedNumber: decision == Decision.accept ? 42 : null,
      zarmaText: decision == Decision.accept ? 'waranka cindi hinka' : '',
      normalizedText: '',
      confidence: 0.95,
      decision: decision,
      modelVersion: 'mock',
      grammarVersion: 'v1',
    );
