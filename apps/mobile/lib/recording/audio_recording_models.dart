import 'package:zarma_mobile/recording/microphone_permission.dart';

enum RecordingPhase {
  idle,
  requestingPermission,
  permissionDenied,
  permissionPermanentlyDenied,
  recording,
  validating,
  ready,
  invalid,
  error,
}

class AudioHandoff {
  const AudioHandoff({
    required this.path,
    required this.duration,
    required this.sizeBytes,
  });

  final String path;
  final Duration duration;
  final int sizeBytes;
}

class AudioFileInspection {
  const AudioFileInspection({
    required this.exists,
    required this.sizeBytes,
    required this.duration,
    required this.isFormatValid,
  });

  const AudioFileInspection.missing()
      : exists = false,
        sizeBytes = 0,
        duration = Duration.zero,
        isFormatValid = false;

  final bool exists;
  final int sizeBytes;
  final Duration duration;
  final bool isFormatValid;
}

class RecordingState {
  const RecordingState({
    this.phase = RecordingPhase.idle,
    this.permission,
    this.elapsed = Duration.zero,
    this.level = 0,
    this.message,
    this.handoff,
  });

  final RecordingPhase phase;
  final MicrophonePermissionStatus? permission;
  final Duration elapsed;
  final double level;
  final String? message;
  final AudioHandoff? handoff;

  bool get isApproachingLimit =>
      elapsed >= RecordingConstraints.idealMaximumDuration;

  RecordingState copyWith({
    RecordingPhase? phase,
    MicrophonePermissionStatus? permission,
    bool clearPermission = false,
    Duration? elapsed,
    double? level,
    String? message,
    bool clearMessage = false,
    AudioHandoff? handoff,
    bool clearHandoff = false,
  }) {
    return RecordingState(
      phase: phase ?? this.phase,
      permission: clearPermission ? null : permission ?? this.permission,
      elapsed: elapsed ?? this.elapsed,
      level: level ?? this.level,
      message: clearMessage ? null : message ?? this.message,
      handoff: clearHandoff ? null : handoff ?? this.handoff,
    );
  }
}

abstract final class RecordingConstraints {
  static const Duration minimumDuration = Duration(seconds: 1);
  static const Duration idealMaximumDuration = Duration(seconds: 8);
  static const Duration maximumDuration = Duration(seconds: 10);
  static const int maximumSizeBytes = 2 * 1024 * 1024;
  static const Duration meterInterval = Duration(milliseconds: 200);
}
