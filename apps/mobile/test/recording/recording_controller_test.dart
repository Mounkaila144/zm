import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:zarma_mobile/recording/audio_recording_models.dart';
import 'package:zarma_mobile/recording/audio_recording_service.dart';
import 'package:zarma_mobile/recording/microphone_permission.dart';
import 'package:zarma_mobile/recording/recording_controller.dart';
import 'package:zarma_mobile/recording/recording_ticker.dart';

class MockAudioRecordingService extends Mock implements AudioRecordingService {}

class MockMicrophonePermissionGateway extends Mock
    implements MicrophonePermissionGateway {}

class FakeRecordingTicker implements RecordingTicker {
  final StreamController<Duration> controller =
      StreamController<Duration>.broadcast();
  bool isDisposed = false;

  @override
  Stream<Duration> get ticks => controller.stream;

  void emit(Duration elapsed) => controller.add(elapsed);

  @override
  Future<void> dispose() async {
    isDisposed = true;
    await controller.close();
  }
}

void main() {
  late MockAudioRecordingService service;
  late MockMicrophonePermissionGateway permissionGateway;
  late StreamController<double> amplitudes;
  late FakeRecordingTicker ticker;
  late RecordingController controller;
  late bool controllerDisposed;

  setUp(() {
    service = MockAudioRecordingService();
    permissionGateway = MockMicrophonePermissionGateway();
    amplitudes = StreamController<double>.broadcast();
    ticker = FakeRecordingTicker();
    controllerDisposed = false;

    when(() => service.cancel()).thenAnswer((_) async {});
    when(() => service.deleteTemporary(any())).thenAnswer((_) async {});
    when(() => service.amplitudeLevels()).thenAnswer((_) => amplitudes.stream);
    when(() => permissionGateway.check()).thenAnswer(
      (_) async => MicrophonePermissionStatus.granted,
    );
    when(() => permissionGateway.request()).thenAnswer(
      (_) async => MicrophonePermissionStatus.granted,
    );
    when(() => permissionGateway.openSettings()).thenAnswer((_) async => true);
    when(() => service.start()).thenAnswer((_) async => '/tmp/take.wav');
    when(() => service.stop()).thenAnswer((_) async => '/tmp/take.wav');
    when(() => service.inspect(any())).thenAnswer(
      (_) async => const AudioFileInspection(
        exists: true,
        sizeBytes: 32044,
        duration: Duration(seconds: 1),
        isFormatValid: true,
      ),
    );

    controller = RecordingController(
      service: service,
      permissionGateway: permissionGateway,
      tickerFactory: () {
        ticker = FakeRecordingTicker();
        return ticker;
      },
    );
  });

  tearDown(() async {
    if (!controllerDisposed) {
      controller.dispose();
    }
    if (!amplitudes.isClosed) {
      await amplitudes.close();
    }
  });

  test('centralise les bornes client', () {
    expect(RecordingConstraints.minimumDuration, const Duration(seconds: 1));
    expect(
      RecordingConstraints.idealMaximumDuration,
      const Duration(seconds: 8),
    );
    expect(RecordingConstraints.maximumDuration, const Duration(seconds: 10));
    expect(RecordingConstraints.maximumSizeBytes, 2 * 1024 * 1024);
  });

  test('démarre une seule capture malgré un double tap', () async {
    await Future.wait(<Future<void>>[controller.start(), controller.start()]);

    expect(controller.state.phase, RecordingPhase.recording);
    verify(() => service.start()).called(1);
  });

  test('publie le temps et le niveau depuis les effets isolés', () async {
    await controller.start();

    ticker.emit(const Duration(seconds: 3));
    amplitudes.add(0.42);
    await pumpEventQueue();

    expect(controller.state.elapsed, const Duration(seconds: 3));
    expect(controller.state.level, closeTo(0.42, 0.001));
  });

  test('start, stop et cancel sont idempotents', () async {
    await controller.start();
    await Future.wait(<Future<void>>[controller.stop(), controller.stop()]);
    await Future.wait(<Future<void>>[controller.cancel(), controller.cancel()]);

    verify(() => service.start()).called(1);
    verify(() => service.stop()).called(1);
    expect(controller.state.phase, RecordingPhase.idle);
  });

  test('dispose nettoie une capture active lors de la navigation', () async {
    await controller.start();

    controller.dispose();
    controllerDisposed = true;
    await pumpEventQueue();

    verify(() => service.cancel()).called(1);
  });

  test('permission accordée démarre sans nouvelle demande', () async {
    await controller.start();

    verify(() => permissionGateway.check()).called(1);
    verifyNever(() => permissionGateway.request());
    verify(() => service.start()).called(1);
    expect(controller.state.permission, MicrophonePermissionStatus.granted);
  });

  test('permission refusée explique le besoin et permet de réessayer',
      () async {
    when(() => permissionGateway.check()).thenAnswer(
      (_) async => MicrophonePermissionStatus.denied,
    );
    when(() => permissionGateway.request()).thenAnswer(
      (_) async => MicrophonePermissionStatus.denied,
    );

    await controller.start();

    expect(controller.state.phase, RecordingPhase.permissionDenied);
    expect(controller.state.message, contains('micro'));
    verifyNever(() => service.start());

    when(() => permissionGateway.request()).thenAnswer(
      (_) async => MicrophonePermissionStatus.granted,
    );
    await controller.start();
    expect(controller.state.phase, RecordingPhase.recording);
  });

  test('refus permanent ouvre les réglages et recontrôle au retour', () async {
    when(() => permissionGateway.check()).thenAnswer(
      (_) async => MicrophonePermissionStatus.permanentlyDenied,
    );

    await controller.start();

    expect(
      controller.state.phase,
      RecordingPhase.permissionPermanentlyDenied,
    );
    verifyNever(() => permissionGateway.request());
    verifyNever(() => service.start());

    await controller.openSettings();
    verify(() => permissionGateway.openSettings()).called(1);

    when(() => permissionGateway.check()).thenAnswer(
      (_) async => MicrophonePermissionStatus.granted,
    );
    await controller.refreshPermission();
    expect(controller.state.phase, RecordingPhase.idle);
    expect(controller.state.permission, MicrophonePermissionStatus.granted);
  });

  test('avertit à 8 secondes sans arrêter avant la limite', () async {
    await controller.start();

    ticker.emit(const Duration(seconds: 8));
    await pumpEventQueue();

    expect(controller.state.elapsed, const Duration(seconds: 8));
    expect(controller.state.isApproachingLimit, isTrue);
    verifyNever(() => service.stop());
  });

  test('arrête automatiquement à 10 secondes et ferme les flux', () async {
    await controller.start();

    ticker.emit(const Duration(seconds: 10));
    await pumpEventQueue(times: 20);

    verify(() => service.stop()).called(1);
    expect(controller.state.phase, RecordingPhase.ready);
    expect(ticker.isDisposed, isTrue);
  });

  test('le retour au premier plan recontrôle un refus permanent', () async {
    when(() => permissionGateway.check()).thenAnswer(
      (_) async => MicrophonePermissionStatus.permanentlyDenied,
    );
    await controller.start();

    when(() => permissionGateway.check()).thenAnswer(
      (_) async => MicrophonePermissionStatus.granted,
    );
    await controller.onAppResumed();

    expect(controller.state.phase, RecordingPhase.idle);
    expect(controller.state.permission, MicrophonePermissionStatus.granted);
  });

  for (final Duration duration in <Duration>[
    const Duration(seconds: 1),
    const Duration(seconds: 8),
    const Duration(seconds: 10),
  ]) {
    test('accepte la borne ${duration.inSeconds} seconde(s)', () async {
      when(() => service.inspect(any())).thenAnswer(
        (_) async => AudioFileInspection(
          exists: true,
          sizeBytes: 32044 * duration.inSeconds,
          duration: duration,
          isFormatValid: true,
        ),
      );

      await controller.start();
      await controller.stop();

      expect(controller.state.phase, RecordingPhase.ready);
      expect(controller.state.handoff?.path, '/tmp/take.wav');
      expect(controller.state.handoff?.duration, duration);
      expect(controller.state.handoff?.sizeBytes, 32044 * duration.inSeconds);
    });
  }

  test('refuse un fichier absent ou vide sans handoff', () async {
    when(
      () => service.inspect(any()),
    ).thenAnswer((_) async => const AudioFileInspection.missing());

    await controller.start();
    await controller.stop();

    expect(controller.state.phase, RecordingPhase.invalid);
    expect(controller.state.handoff, isNull);
    expect(controller.state.message, contains('Aucun'));
    verify(() => service.deleteTemporary('/tmp/take.wav')).called(1);

    when(() => service.inspect(any())).thenAnswer(
      (_) async => const AudioFileInspection(
        exists: true,
        sizeBytes: 0,
        duration: Duration.zero,
        isFormatValid: true,
      ),
    );
    await controller.start();
    await controller.stop();
    expect(controller.state.phase, RecordingPhase.invalid);
    expect(controller.state.handoff, isNull);
  });

  test('refuse les durées sous 1 seconde et au-dessus de 10 secondes',
      () async {
    when(() => service.inspect(any())).thenAnswer(
      (_) async => const AudioFileInspection(
        exists: true,
        sizeBytes: 30000,
        duration: Duration(milliseconds: 999),
        isFormatValid: true,
      ),
    );
    await controller.start();
    await controller.stop();
    expect(controller.state.phase, RecordingPhase.invalid);
    expect(controller.state.message, contains('une seconde'));

    when(() => service.inspect(any())).thenAnswer(
      (_) async => const AudioFileInspection(
        exists: true,
        sizeBytes: 321000,
        duration: Duration(milliseconds: 10001),
        isFormatValid: true,
      ),
    );
    await controller.start();
    await controller.stop();
    expect(controller.state.phase, RecordingPhase.invalid);
    expect(controller.state.message, contains('dix secondes'));
  });

  test('refuse un WAV invalide et un fichier au-dessus de 2 Mo', () async {
    when(() => service.inspect(any())).thenAnswer(
      (_) async => const AudioFileInspection(
        exists: true,
        sizeBytes: 32044,
        duration: Duration(seconds: 1),
        isFormatValid: false,
      ),
    );
    await controller.start();
    await controller.stop();
    expect(controller.state.phase, RecordingPhase.invalid);
    expect(controller.state.message, contains('format'));

    when(() => service.inspect(any())).thenAnswer(
      (_) async => const AudioFileInspection(
        exists: true,
        sizeBytes: RecordingConstraints.maximumSizeBytes + 1,
        duration: Duration(seconds: 5),
        isFormatValid: true,
      ),
    );
    await controller.start();
    await controller.stop();
    expect(controller.state.phase, RecordingPhase.invalid);
    expect(controller.state.message, contains('volumineux'));
  });

  test('annulation ferme la capture et supprime le temporaire', () async {
    await controller.start();

    await controller.cancel();

    verify(() => service.cancel()).called(1);
    verify(() => service.deleteTemporary('/tmp/take.wav')).called(1);
    expect(controller.state.phase, RecordingPhase.idle);
    expect(controller.state.handoff, isNull);
  });

  test('nettoie après une erreur de démarrage ou d’arrêt', () async {
    when(() => service.start()).thenThrow(StateError('plugin start'));

    await controller.start();

    expect(controller.state.phase, RecordingPhase.error);
    verify(() => service.cancel()).called(1);

    when(() => service.start()).thenAnswer((_) async => '/tmp/take.wav');
    when(() => service.stop()).thenThrow(StateError('plugin stop'));
    await controller.start();
    await controller.stop();

    expect(controller.state.phase, RecordingPhase.error);
    verify(() => service.deleteTemporary('/tmp/take.wav')).called(1);
  });

  test('une nouvelle prise supprime le handoff précédent', () async {
    await controller.start();
    await controller.stop();
    expect(controller.state.handoff, isNotNull);

    await controller.start();

    verify(() => service.deleteTemporary('/tmp/take.wav')).called(1);
    expect(controller.state.handoff, isNull);
    expect(controller.state.phase, RecordingPhase.recording);
  });

  test('la suppression post-envoi simulé est explicite et idempotente',
      () async {
    await controller.start();
    await controller.stop();

    await controller.deleteHandoff();
    await controller.deleteHandoff();

    verify(() => service.deleteTemporary('/tmp/take.wav')).called(1);
    expect(controller.state.handoff, isNull);
    expect(controller.state.phase, RecordingPhase.idle);
  });
}
