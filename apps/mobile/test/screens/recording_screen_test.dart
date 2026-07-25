import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:zarma_mobile/navigation/app_routes.dart';
import 'package:zarma_mobile/recording/audio_recording_models.dart';
import 'package:zarma_mobile/recording/audio_recording_service.dart';
import 'package:zarma_mobile/recording/microphone_permission.dart';
import 'package:zarma_mobile/recording/recording_controller.dart';
import 'package:zarma_mobile/recording/recording_ticker.dart';
import 'package:zarma_mobile/screens/processing_screen.dart';
import 'package:zarma_mobile/screens/recording_screen.dart';

class MockWidgetAudioService extends Mock implements AudioRecordingService {}

class MockWidgetPermissionGateway extends Mock
    implements MicrophonePermissionGateway {}

class ControlledRecordingTicker implements RecordingTicker {
  final StreamController<Duration> controller =
      StreamController<Duration>.broadcast();

  @override
  Stream<Duration> get ticks => controller.stream;

  void emit(Duration elapsed) => controller.add(elapsed);

  @override
  Future<void> dispose() async {
    if (!controller.isClosed) {
      await controller.close();
    }
  }
}

class WidgetRecordingController extends RecordingController {
  WidgetRecordingController({
    required super.service,
    required super.permissionGateway,
    required super.tickerFactory,
  });

  void setStateForTest(RecordingState value) {
    state = value;
  }
}

class RecordingWidgetHarness {
  RecordingWidgetHarness() {
    when(() => service.cancel()).thenAnswer((_) async {});
    when(() => service.deleteTemporary(any())).thenAnswer((_) async {});
    when(() => service.amplitudeLevels()).thenAnswer((_) => amplitudes.stream);
    when(() => service.start()).thenAnswer((_) async => '/tmp/widget.wav');
    when(() => service.stop()).thenAnswer((_) async => '/tmp/widget.wav');
    when(() => service.inspect(any())).thenAnswer(
      (_) async => const AudioFileInspection(
        exists: true,
        sizeBytes: 64044,
        duration: Duration(seconds: 2),
        isFormatValid: true,
      ),
    );
    when(() => permission.check()).thenAnswer(
      (_) async => MicrophonePermissionStatus.granted,
    );
    when(() => permission.request()).thenAnswer(
      (_) async => MicrophonePermissionStatus.granted,
    );
    when(() => permission.openSettings()).thenAnswer((_) async => true);

    controller = WidgetRecordingController(
      service: service,
      permissionGateway: permission,
      tickerFactory: () {
        ticker = ControlledRecordingTicker();
        return ticker;
      },
    );
  }

  final MockWidgetAudioService service = MockWidgetAudioService();
  final MockWidgetPermissionGateway permission = MockWidgetPermissionGateway();
  final StreamController<double> amplitudes =
      StreamController<double>.broadcast();
  late ControlledRecordingTicker ticker;
  late WidgetRecordingController controller;
}

void main() {
  testWidgets('affiche les parcours refusé et refus permanent avec actions', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle semantics = tester.ensureSemantics();
    final RecordingWidgetHarness harness = RecordingWidgetHarness();
    when(() => harness.permission.check()).thenAnswer(
      (_) async => MicrophonePermissionStatus.denied,
    );
    when(() => harness.permission.request()).thenAnswer(
      (_) async => MicrophonePermissionStatus.denied,
    );
    await _pumpRecordingScreen(tester, harness);

    await tester.tap(find.byKey(const Key('begin-recording-button')));
    await tester.pumpAndSettle();
    expect(find.byIcon(Icons.mic_off_outlined), findsOneWidget);
    expect(find.textContaining('micro est nécessaire'), findsOneWidget);
    expect(
      find.bySemanticsLabel('Réessayer l’autorisation du micro'),
      findsOneWidget,
    );

    when(() => harness.permission.check()).thenAnswer(
      (_) async => MicrophonePermissionStatus.permanentlyDenied,
    );
    await tester.tap(find.byKey(const Key('retry-permission-button')));
    await tester.pumpAndSettle();
    expect(find.byIcon(Icons.settings_outlined), findsOneWidget);
    expect(find.byKey(const Key('open-settings-button')), findsOneWidget);

    await tester.tap(find.byKey(const Key('open-settings-button')));
    await tester.pump();
    verify(() => harness.permission.openSettings()).called(1);
    semantics.dispose();
    await _disposeHarness(tester);
  });

  testWidgets('affiche minuterie, niveau, limite et actions accessibles', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle semantics = tester.ensureSemantics();
    final RecordingWidgetHarness harness = RecordingWidgetHarness();
    await _pumpRecordingScreen(tester, harness);

    await tester.tap(find.byKey(const Key('begin-recording-button')));
    await tester.pumpAndSettle();

    harness.ticker.emit(const Duration(milliseconds: 2500));
    harness.amplitudes.add(0.75);
    await tester.pump();
    await tester.pump();
    expect(find.text('00:02.5'), findsOneWidget);
    final LinearProgressIndicator level = tester.widget(
      find.byKey(const Key('audio-level-indicator')),
    );
    expect(level.value, closeTo(0.75, 0.001));
    expect(
      find.bySemanticsLabel(
        RegExp('Micro actif.*Niveau audio 75 pour cent'),
      ),
      findsOneWidget,
    );
    expect(
      tester.getSize(find.byKey(const Key('stop-recording-button'))).height,
      greaterThanOrEqualTo(48),
    );

    harness.ticker.emit(const Duration(seconds: 8));
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('Limite proche'), findsOneWidget);
    expect(find.byKey(const Key('active-microphone-icon')), findsOneWidget);

    semantics.dispose();
    await _disposeHarness(tester);
  });

  testWidgets('navigue vers Traitement uniquement avec un handoff valide', (
    WidgetTester tester,
  ) async {
    final RecordingWidgetHarness harness = RecordingWidgetHarness();
    harness.controller.setStateForTest(
      const RecordingState(
        phase: RecordingPhase.ready,
        permission: MicrophonePermissionStatus.granted,
        elapsed: Duration(seconds: 2),
        message: 'Audio prêt à être traité.',
        handoff: AudioHandoff(
          path: '/tmp/widget.wav',
          duration: Duration(seconds: 2),
          sizeBytes: 64044,
        ),
      ),
    );
    await _pumpRecordingScreen(tester, harness);

    expect(find.byKey(const Key('continue-processing-button')), findsOneWidget);
    await tester.tap(find.byKey(const Key('continue-processing-button')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    expect(find.byKey(const Key('processing-screen')), findsOneWidget);
    await _disposeHarness(tester);
  });

  testWidgets('audio invalide et erreur proposent une reprise sans navigation',
      (
    WidgetTester tester,
  ) async {
    final RecordingWidgetHarness harness = RecordingWidgetHarness();
    harness.controller.setStateForTest(
      const RecordingState(
        phase: RecordingPhase.invalid,
        permission: MicrophonePermissionStatus.granted,
        message: 'Aucun son exploitable n’a été enregistré.',
      ),
    );
    await _pumpRecordingScreen(tester, harness);

    expect(find.byKey(const Key('retry-recording-button')), findsOneWidget);
    expect(find.byKey(const Key('continue-processing-button')), findsNothing);
    expect(find.textContaining('Aucun son'), findsOneWidget);
    await _disposeHarness(tester);
  });
}

Future<void> _pumpRecordingScreen(
  WidgetTester tester,
  RecordingWidgetHarness harness,
) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: <Override>[
        recordingControllerProvider.overrideWith((ref) => harness.controller),
      ],
      child: MaterialApp(
        routes: <String, WidgetBuilder>{
          AppRoutes.processing: (_) => const ProcessingScreen(
                handoff: AudioHandoff(
                  path: '/tmp/valid.wav',
                  duration: Duration(seconds: 2),
                  sizeBytes: 64044,
                ),
              ),
        },
        home: const RecordingScreen(),
      ),
    ),
  );
  await tester.pump();
}

Future<void> _disposeHarness(
  WidgetTester tester,
) async {
  await tester.pumpWidget(const SizedBox.shrink());
  await tester.pump();
}
