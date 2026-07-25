import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:zarma_mobile/app.dart';
import 'package:zarma_mobile/models/recognition_result.dart';
import 'package:zarma_mobile/navigation/app_routes.dart';
import 'package:zarma_mobile/recognition/recognition_repository.dart';
import 'package:zarma_mobile/recording/audio_recording_models.dart';

class _PendingRecognitionRepository implements RecognitionRepository {
  @override
  Future<RecognitionResult> recognize({
    required AudioHandoff handoff,
    required String anonId,
    required CancelToken cancelToken,
  }) async {
    await cancelToken.whenCancel;
    throw const RecognitionFailure(
      type: RecognitionFailureType.cancelled,
      message: '',
    );
  }
}

void main() {
  testWidgets('démarre sur l’écran Accueil dans un ProviderScope', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle semantics = tester.ensureSemantics();

    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          recognitionRepositoryProvider.overrideWithValue(
            _PendingRecognitionRepository(),
          ),
        ],
        child: const ZarmaApp(),
      ),
    );

    expect(find.text('Accueil'), findsOneWidget);
    expect(find.byIcon(Icons.mic), findsOneWidget);
    expect(find.byKey(const Key('open-history-button')), findsNothing);
    expect(find.byKey(const Key('open-contribution-button')), findsNothing);
    expect(
      find.bySemanticsLabel('Démarrer un enregistrement audio'),
      findsOneWidget,
    );
    final Size microphoneButtonSize = tester.getSize(
      find.byKey(const Key('start-recording-button')),
    );
    expect(microphoneButtonSize.width, greaterThanOrEqualTo(48));
    expect(microphoneButtonSize.height, greaterThanOrEqualTo(48));
    expect(find.byType(MaterialApp), findsOneWidget);
    final MaterialApp app = tester.widget(find.byType(MaterialApp));
    expect(app.theme?.useMaterial3, isTrue);
    semantics.dispose();
  });

  testWidgets('les destinations restent navigables avec un accueil simplifié', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          recognitionRepositoryProvider.overrideWithValue(
            _PendingRecognitionRepository(),
          ),
        ],
        child: const ZarmaApp(),
      ),
    );

    expect(find.byKey(const Key('home-screen')), findsOneWidget);
    expect(AppRoutes.routes.containsKey(AppRoutes.recording), isTrue);

    final NavigatorState navigator = tester.state(find.byType(Navigator));
    navigator.pushNamed(
      AppRoutes.processing,
      arguments: const AudioHandoff(
        path: '/tmp/take.wav',
        duration: Duration(seconds: 2),
        sizeBytes: 64044,
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    expect(find.byKey(const Key('processing-screen')), findsOneWidget);

    await tester.pageBack();
    await tester.pumpAndSettle();
    const RecognitionResult result = RecognitionResult(
      id: 'id',
      recognizedNumber: 42,
      zarmaText: 'waranka cindi hinka',
      normalizedText: 'waranka cindi hinka',
      confidence: 0.95,
      decision: Decision.accept,
      modelVersion: 'mock',
      grammarVersion: 'v1',
    );
    navigator.pushNamed(AppRoutes.result, arguments: result);
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('result-screen')), findsOneWidget);

    navigator.pushNamed(AppRoutes.confirmation, arguments: result);
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('confirmation-screen')), findsOneWidget);

    await tester.pageBack();
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('open-correction-button')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('correction-screen')), findsOneWidget);

    for (int index = 0; index < 2; index++) {
      await tester.pageBack();
      await tester.pumpAndSettle();
    }
    expect(find.byKey(const Key('home-screen')), findsOneWidget);

    navigator.pushNamed(AppRoutes.history);
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('history-screen')), findsOneWidget);

    await tester.pageBack();
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('home-screen')), findsOneWidget);
  });
}
