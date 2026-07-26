import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zarma_mobile/recording/audio_recording_models.dart';
import 'package:zarma_mobile/recording/audio_recording_service.dart';
import 'package:zarma_mobile/recording/microphone_permission.dart';
import 'package:zarma_mobile/recording/recording_ticker.dart';

typedef RecordingTickerFactory = RecordingTicker Function();

class RecordingController extends StateNotifier<RecordingState> {
  RecordingController({
    required this._service,
    required this._permissionGateway,
    required this._tickerFactory,
  })  : super(const RecordingState());

  final AudioRecordingService _service;
  final MicrophonePermissionGateway _permissionGateway;
  final RecordingTickerFactory _tickerFactory;
  Future<void> _operation = Future<void>.value();
  RecordingTicker? _ticker;
  StreamSubscription<Duration>? _tickerSubscription;
  StreamSubscription<double>? _amplitudeSubscription;
  String? _activePath;
  bool _automaticStopScheduled = false;

  Future<void> start() => _serialize(_start);

  Future<void> stop() => _serialize(_stop);

  Future<void> cancel() => _serialize(_cancel);

  Future<void> deleteHandoff() => _serialize(_deleteHandoff);

  Future<void> refreshPermission() => _serialize(_refreshPermission);

  Future<void> openSettings() => _serialize(_openSettings);

  Future<void> onAppResumed() => _serialize(_onAppResumed);

  Future<void> _start() async {
    if (state.phase == RecordingPhase.recording ||
        state.phase == RecordingPhase.requestingPermission ||
        state.phase == RecordingPhase.validating) {
      return;
    }

    await _deleteHandoff();
    state = state.copyWith(
      phase: RecordingPhase.requestingPermission,
      elapsed: Duration.zero,
      level: 0,
      clearMessage: true,
      clearHandoff: true,
    );

    try {
      MicrophonePermissionStatus permission = await _permissionGateway.check();
      if (permission == MicrophonePermissionStatus.denied) {
        permission = await _permissionGateway.request();
      }
      if (permission != MicrophonePermissionStatus.granted) {
        _setPermissionFailure(permission);
        return;
      }

      _activePath = await _service.start();
      _startMeters();
      state = state.copyWith(
        phase: RecordingPhase.recording,
        permission: permission,
        elapsed: Duration.zero,
        level: 0,
        clearMessage: true,
      );
    } catch (_) {
      await _cleanupCapture();
      state = state.copyWith(
        phase: RecordingPhase.error,
        message: 'Impossible de démarrer l’enregistrement. Réessayez.',
        clearHandoff: true,
      );
    }
  }

  Future<void> _stop() async {
    if (state.phase != RecordingPhase.recording) {
      return;
    }
    state = state.copyWith(
      phase: RecordingPhase.validating,
      message: 'Vérification de l’audio…',
    );
    await _stopMeters();

    try {
      final String? path = await _service.stop();
      _activePath = path ?? _activePath;
      if (_activePath == null) {
        await _setInvalid('Aucun fichier audio n’a été créé.');
        return;
      }

      final AudioFileInspection inspection = await _service.inspect(
        _activePath!,
      );
      final String? validationMessage = _validationMessage(inspection);
      if (validationMessage != null) {
        await _setInvalid(validationMessage);
        return;
      }

      state = state.copyWith(
        phase: RecordingPhase.ready,
        elapsed: inspection.duration,
        level: 0,
        message: 'Audio prêt à être traité.',
        handoff: AudioHandoff(
          path: _activePath!,
          duration: inspection.duration,
          sizeBytes: inspection.sizeBytes,
        ),
      );
    } catch (_) {
      await _cleanupCapture();
      state = state.copyWith(
        phase: RecordingPhase.error,
        level: 0,
        message: 'Impossible de finaliser l’audio. Recommencez.',
        clearHandoff: true,
      );
    }
  }

  Future<void> _cancel() async {
    await _stopMeters();
    final String? handoffPath = state.handoff?.path;
    try {
      await _service.cancel();
    } finally {
      await _service.deleteTemporary(_activePath);
      await _service.deleteTemporary(handoffPath);
      _activePath = null;
      state = RecordingState(permission: state.permission);
    }
  }

  Future<void> _deleteHandoff() async {
    final String? handoffPath = state.handoff?.path;
    if (handoffPath == null) {
      if (state.phase == RecordingPhase.ready) {
        state = state.copyWith(
          phase: RecordingPhase.idle,
          elapsed: Duration.zero,
          level: 0,
          message: 'Vous pouvez enregistrer un nouveau nombre.',
          clearHandoff: true,
        );
      }
      return;
    }
    await _service.deleteTemporary(handoffPath);
    if (_activePath == handoffPath) {
      _activePath = null;
    }
    state = state.copyWith(
      phase: RecordingPhase.idle,
      elapsed: Duration.zero,
      level: 0,
      message: 'Vous pouvez enregistrer un nouveau nombre.',
      clearHandoff: true,
    );
  }

  Future<void> _refreshPermission() async {
    final MicrophonePermissionStatus permission =
        await _permissionGateway.check();
    if (permission == MicrophonePermissionStatus.granted) {
      state = state.copyWith(
        phase: RecordingPhase.idle,
        permission: permission,
        message: 'Permission accordée. Vous pouvez enregistrer.',
      );
      return;
    }
    _setPermissionFailure(permission);
  }

  Future<void> _openSettings() async {
    await _permissionGateway.openSettings();
  }

  Future<void> _onAppResumed() async {
    if (state.phase == RecordingPhase.permissionPermanentlyDenied) {
      await _refreshPermission();
    }
  }

  void _setPermissionFailure(MicrophonePermissionStatus permission) {
    if (permission == MicrophonePermissionStatus.permanentlyDenied) {
      state = state.copyWith(
        phase: RecordingPhase.permissionPermanentlyDenied,
        permission: permission,
        message:
            'Autorisez le micro dans les réglages pour enregistrer votre voix.',
        clearHandoff: true,
      );
      return;
    }
    state = state.copyWith(
      phase: RecordingPhase.permissionDenied,
      permission: permission,
      message: 'Le micro est nécessaire pour enregistrer un nombre.',
      clearHandoff: true,
    );
  }

  void _startMeters() {
    _automaticStopScheduled = false;
    _ticker = _tickerFactory();
    _tickerSubscription = _ticker!.ticks.listen(_onTick);
    _amplitudeSubscription = _service.amplitudeLevels().listen(
      (double level) {
        if (mounted && state.phase == RecordingPhase.recording) {
          state = state.copyWith(level: level.clamp(0.0, 1.0).toDouble());
        }
      },
      onError: (_) {
        if (mounted && state.phase == RecordingPhase.recording) {
          state = state.copyWith(level: 0);
        }
      },
    );
  }

  void _onTick(Duration elapsed) {
    if (!mounted || state.phase != RecordingPhase.recording) {
      return;
    }
    final Duration bounded = elapsed > RecordingConstraints.maximumDuration
        ? RecordingConstraints.maximumDuration
        : elapsed;
    state = state.copyWith(elapsed: bounded);
    if (elapsed >= RecordingConstraints.maximumDuration &&
        !_automaticStopScheduled) {
      _automaticStopScheduled = true;
      unawaited(stop());
    }
  }

  String? _validationMessage(AudioFileInspection inspection) {
    if (!inspection.exists || inspection.sizeBytes == 0) {
      return 'Aucun son exploitable n’a été enregistré.';
    }
    if (!inspection.isFormatValid) {
      return 'Le format audio est invalide. Recommencez.';
    }
    if (inspection.duration < RecordingConstraints.minimumDuration) {
      return 'Parlez au moins une seconde, puis réessayez.';
    }
    if (inspection.duration > RecordingConstraints.maximumDuration) {
      return 'L’enregistrement dépasse dix secondes. Recommencez.';
    }
    if (inspection.sizeBytes > RecordingConstraints.maximumSizeBytes) {
      return 'L’enregistrement est trop volumineux. Recommencez.';
    }
    return null;
  }

  Future<void> _setInvalid(String message) async {
    await _service.deleteTemporary(_activePath);
    _activePath = null;
    state = state.copyWith(
      phase: RecordingPhase.invalid,
      level: 0,
      message: message,
      clearHandoff: true,
    );
  }

  Future<void> _cleanupCapture() async {
    await _stopMeters();
    try {
      await _service.cancel();
    } finally {
      await _service.deleteTemporary(_activePath);
      _activePath = null;
    }
  }

  Future<void> _stopMeters() async {
    await _tickerSubscription?.cancel();
    _tickerSubscription = null;
    await _amplitudeSubscription?.cancel();
    _amplitudeSubscription = null;
    await _ticker?.dispose();
    _ticker = null;
    _automaticStopScheduled = false;
  }

  Future<void> _serialize(Future<void> Function() action) {
    final Future<void> next = _operation.then<void>((_) => action());
    _operation = next.then<void>(
      (_) {},
      onError: (_, __) {},
    );
    return next;
  }

  @override
  void dispose() {
    unawaited(_stopMeters());
    unawaited(_service.cancel());
    super.dispose();
  }
}

final microphonePermissionProvider = Provider<MicrophonePermissionGateway>((
  ref,
) {
  return const PermissionHandlerMicrophonePermission();
});

final audioRecordingServiceProvider = Provider<AudioRecordingService>((ref) {
  final PluginAudioRecordingService service = PluginAudioRecordingService();
  ref.onDispose(() => unawaited(service.dispose()));
  return service;
});

final recordingTickerFactoryProvider = Provider<RecordingTickerFactory>((ref) {
  return PeriodicRecordingTicker.new;
});

final recordingControllerProvider =
    StateNotifierProvider.autoDispose<RecordingController, RecordingState>((
  ref,
) {
  return RecordingController(
    service: ref.watch(audioRecordingServiceProvider),
    permissionGateway: ref.watch(microphonePermissionProvider),
    tickerFactory: ref.watch(recordingTickerFactoryProvider),
  );
});
