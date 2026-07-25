import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:path_provider/path_provider.dart';
import 'package:record/record.dart';
import 'package:zarma_mobile/recording/audio_recording_models.dart';

abstract interface class AudioRecordingService {
  Future<String> start();

  Future<String?> stop();

  Future<void> cancel();

  Stream<double> amplitudeLevels();

  Future<AudioFileInspection> inspect(String path);

  Future<void> deleteTemporary(String? path);

  Future<void> dispose();
}

class PluginAudioRecordingService implements AudioRecordingService {
  PluginAudioRecordingService({
    AudioRecorder? recorder,
    Future<Directory> Function()? temporaryDirectory,
    DateTime Function()? now,
  })  : _recorder = recorder ?? AudioRecorder(),
        _temporaryDirectory = temporaryDirectory ?? getTemporaryDirectory,
        _now = now ?? DateTime.now;

  static const RecordConfig recordingConfig = RecordConfig(
    encoder: AudioEncoder.wav,
    sampleRate: 16000,
    numChannels: 1,
  );

  final AudioRecorder _recorder;
  final Future<Directory> Function() _temporaryDirectory;
  final DateTime Function() _now;
  String? _activePath;
  bool _isRecording = false;
  bool _isDisposed = false;
  int _sequence = 0;

  @override
  Future<String> start() async {
    if (_isDisposed) {
      throw StateError('AudioRecordingService is disposed.');
    }
    await cancel();
    final Directory directory = await _temporaryDirectory();
    final String path = '${directory.path}/zarma_recording_'
        '${_now().microsecondsSinceEpoch}_${_sequence++}.wav';
    _activePath = path;

    try {
      await _recorder.start(recordingConfig, path: path);
      _isRecording = true;
      return path;
    } catch (_) {
      await deleteTemporary(path);
      rethrow;
    }
  }

  @override
  Future<String?> stop() async {
    if (!_isRecording) {
      return _activePath;
    }
    final String? outputPath = await _recorder.stop();
    _isRecording = false;
    _activePath = outputPath ?? _activePath;
    if (_activePath != null) {
      await constrainWavDuration(
        _activePath!,
        RecordingConstraints.maximumDuration,
      );
    }
    return _activePath;
  }

  @override
  Future<void> cancel() async {
    final String? path = _activePath;
    try {
      if (_isRecording) {
        await _recorder.cancel();
      }
    } finally {
      _isRecording = false;
      await deleteTemporary(path);
    }
  }

  @override
  Stream<double> amplitudeLevels() {
    // record 5.x keeps a single-subscription amplitude controller alive after
    // cancellation, so a second recording cannot listen to it again. Polling
    // getAmplitude creates an independent, cancellable stream for every take.
    return Stream<void>.periodic(RecordingConstraints.meterInterval)
        .asyncMap((_) => _recorder.getAmplitude())
        .map((Amplitude amplitude) {
      return ((amplitude.current + 60) / 60).clamp(0.0, 1.0).toDouble();
    });
  }

  @override
  Future<AudioFileInspection> inspect(String path) => inspectWavFile(path);

  @override
  Future<void> deleteTemporary(String? path) async {
    if (path == null || path.isEmpty) {
      return;
    }
    final File file = File(path);
    if (await file.exists()) {
      await file.delete();
    }
    if (_activePath == path) {
      _activePath = null;
    }
  }

  @override
  Future<void> dispose() async {
    if (_isDisposed) {
      return;
    }
    _isDisposed = true;
    await cancel();
    await _recorder.dispose();
  }
}

Future<void> constrainWavDuration(String path, Duration maximumDuration) async {
  final File file = File(path);
  if (!await file.exists()) {
    return;
  }

  final Uint8List bytes = await file.readAsBytes();
  if (bytes.length < 44 ||
      _ascii(bytes, 0, 4) != 'RIFF' ||
      _ascii(bytes, 8, 4) != 'WAVE') {
    return;
  }

  final ByteData data = ByteData.sublistView(bytes);
  int? dataHeaderOffset;
  int? dataContentStart;
  int? dataSize;
  int? byteRate;
  int? blockAlign;
  int offset = 12;

  while (offset + 8 <= bytes.length) {
    final String chunkId = _ascii(bytes, offset, 4);
    final int chunkSize = data.getUint32(offset + 4, Endian.little);
    final int contentStart = offset + 8;
    final int contentEnd = contentStart + chunkSize;
    if (contentEnd > bytes.length) {
      return;
    }

    if (chunkId == 'fmt ' && chunkSize >= 16) {
      byteRate = data.getUint32(contentStart + 8, Endian.little);
      blockAlign = data.getUint16(contentStart + 12, Endian.little);
    } else if (chunkId == 'data') {
      dataHeaderOffset = offset;
      dataContentStart = contentStart;
      dataSize = chunkSize;
      break;
    }
    offset = contentEnd + (chunkSize.isOdd ? 1 : 0);
  }

  if (dataHeaderOffset == null ||
      dataContentStart == null ||
      dataSize == null ||
      byteRate == null ||
      byteRate <= 0 ||
      blockAlign == null ||
      blockAlign <= 0) {
    return;
  }

  final int maximumDataBytes = maximumDuration.inMicroseconds *
      byteRate ~/
      Duration.microsecondsPerSecond ~/
      blockAlign *
      blockAlign;
  if (dataSize <= maximumDataBytes) {
    return;
  }

  final int originalDataEnd = dataContentStart + dataSize;
  final int trailingStart = originalDataEnd + (dataSize.isOdd ? 1 : 0);
  final int trailingLength = bytes.length - trailingStart;
  final Uint8List constrained = Uint8List(
    dataContentStart + maximumDataBytes + trailingLength,
  );
  constrained.setRange(0, dataContentStart, bytes);
  constrained.setRange(
    dataContentStart,
    dataContentStart + maximumDataBytes,
    bytes,
    dataContentStart,
  );
  if (trailingLength > 0) {
    constrained.setRange(
      dataContentStart + maximumDataBytes,
      constrained.length,
      bytes,
      trailingStart,
    );
  }

  final ByteData constrainedData = ByteData.sublistView(constrained);
  constrainedData.setUint32(
    dataHeaderOffset + 4,
    maximumDataBytes,
    Endian.little,
  );
  constrainedData.setUint32(4, constrained.length - 8, Endian.little);
  await file.writeAsBytes(constrained, flush: true);
}

Future<AudioFileInspection> inspectWavFile(String path) async {
  final File file = File(path);
  if (!await file.exists()) {
    return const AudioFileInspection.missing();
  }

  final Uint8List bytes = await file.readAsBytes();
  if (bytes.length < 44 ||
      _ascii(bytes, 0, 4) != 'RIFF' ||
      _ascii(bytes, 8, 4) != 'WAVE') {
    return AudioFileInspection(
      exists: true,
      sizeBytes: bytes.length,
      duration: Duration.zero,
      isFormatValid: false,
    );
  }

  final ByteData data = ByteData.sublistView(bytes);
  int? audioFormat;
  int? channels;
  int? sampleRate;
  int? byteRate;
  int? blockAlign;
  int? bitsPerSample;
  int? dataSize;
  int offset = 12;

  while (offset + 8 <= bytes.length) {
    final String chunkId = _ascii(bytes, offset, 4);
    final int chunkSize = data.getUint32(offset + 4, Endian.little);
    final int contentStart = offset + 8;
    final int contentEnd = contentStart + chunkSize;
    if (contentEnd > bytes.length) {
      break;
    }

    if (chunkId == 'fmt ' && chunkSize >= 16) {
      audioFormat = data.getUint16(contentStart, Endian.little);
      channels = data.getUint16(contentStart + 2, Endian.little);
      sampleRate = data.getUint32(contentStart + 4, Endian.little);
      byteRate = data.getUint32(contentStart + 8, Endian.little);
      blockAlign = data.getUint16(contentStart + 12, Endian.little);
      bitsPerSample = data.getUint16(contentStart + 14, Endian.little);
    } else if (chunkId == 'data') {
      dataSize = chunkSize;
    }

    offset = contentEnd + (chunkSize.isOdd ? 1 : 0);
  }

  final bool isFormatValid = audioFormat == 1 &&
      channels == 1 &&
      sampleRate == 16000 &&
      byteRate == 32000 &&
      blockAlign == 2 &&
      bitsPerSample == 16 &&
      dataSize != null;
  final Duration duration = byteRate != null && byteRate > 0 && dataSize != null
      ? Duration(
          microseconds: (dataSize * Duration.microsecondsPerSecond) ~/ byteRate,
        )
      : Duration.zero;

  return AudioFileInspection(
    exists: true,
    sizeBytes: bytes.length,
    duration: duration,
    isFormatValid: isFormatValid,
  );
}

String _ascii(Uint8List bytes, int offset, int length) {
  return String.fromCharCodes(bytes, offset, offset + length);
}
