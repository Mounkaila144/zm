import 'dart:io';

import 'package:path_provider/path_provider.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:record/record.dart';

class AudioCaptureService {
  AudioCaptureService({AudioRecorder? recorder})
    : _recorder = recorder ?? AudioRecorder();

  // Recopiée volontairement depuis apps/mobile. Les deux applications restent
  // indépendantes.
  static const RecordConfig recordingConfig = RecordConfig(
    encoder: AudioEncoder.wav,
    sampleRate: 16000,
    numChannels: 1,
  );

  final AudioRecorder _recorder;
  String? _temporaryPath;
  bool _recording = false;

  Future<String> start() async {
    final status = await Permission.microphone.request();
    if (!status.isGranted || !await _recorder.hasPermission()) {
      throw const MicrophonePermissionException();
    }
    if (_recording) {
      await cancel();
    }
    final directory = await getTemporaryDirectory();
    final path =
        '${directory.path}/prise_${DateTime.now().microsecondsSinceEpoch}.wav';
    _temporaryPath = path;
    await _recorder.start(recordingConfig, path: path);
    _recording = true;
    return path;
  }

  Future<String?> stop() async {
    if (!_recording) {
      return _temporaryPath;
    }
    final pluginPath = await _recorder.stop();
    _recording = false;
    _temporaryPath = pluginPath ?? _temporaryPath;
    return _temporaryPath;
  }

  Future<void> cancel() async {
    final path = _temporaryPath;
    if (_recording) {
      await _recorder.cancel();
    }
    _recording = false;
    _temporaryPath = null;
    if (path != null) {
      final file = File(path);
      if (await file.exists()) {
        await file.delete();
      }
    }
  }

  Future<void> dispose() async {
    await cancel();
    await _recorder.dispose();
  }
}

class MicrophonePermissionException implements Exception {
  const MicrophonePermissionException();
}
