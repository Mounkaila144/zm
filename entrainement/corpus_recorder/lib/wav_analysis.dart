import 'dart:io';
import 'dart:math' as math;
import 'dart:typed_data';

class WavMetrics {
  const WavMetrics({
    required this.durationSeconds,
    required this.rms,
    required this.peak,
    required this.trailingSilenceSeconds,
    required this.formatValid,
  });

  final double durationSeconds;
  final double rms;
  final double peak;
  final double trailingSilenceSeconds;
  final bool formatValid;
}

Future<WavMetrics> inspectWav(String path) async {
  final bytes = await File(path).readAsBytes();
  if (bytes.length < 44 ||
      _ascii(bytes, 0, 4) != 'RIFF' ||
      _ascii(bytes, 8, 4) != 'WAVE') {
    return const WavMetrics(
      durationSeconds: 0,
      rms: 0,
      peak: 0,
      trailingSilenceSeconds: 0,
      formatValid: false,
    );
  }

  final data = ByteData.sublistView(bytes);
  int? format;
  int? channels;
  int? sampleRate;
  int? byteRate;
  int? blockAlign;
  int? bitsPerSample;
  int? audioStart;
  int? audioSize;
  var offset = 12;
  while (offset + 8 <= bytes.length) {
    final id = _ascii(bytes, offset, 4);
    final size = data.getUint32(offset + 4, Endian.little);
    final start = offset + 8;
    final end = start + size;
    if (end > bytes.length) {
      break;
    }
    if (id == 'fmt ' && size >= 16) {
      format = data.getUint16(start, Endian.little);
      channels = data.getUint16(start + 2, Endian.little);
      sampleRate = data.getUint32(start + 4, Endian.little);
      byteRate = data.getUint32(start + 8, Endian.little);
      blockAlign = data.getUint16(start + 12, Endian.little);
      bitsPerSample = data.getUint16(start + 14, Endian.little);
    } else if (id == 'data') {
      audioStart = start;
      audioSize = size;
      break;
    }
    offset = end + (size.isOdd ? 1 : 0);
  }

  final valid =
      format == 1 &&
      channels == 1 &&
      sampleRate == 16000 &&
      byteRate == 32000 &&
      blockAlign == 2 &&
      bitsPerSample == 16 &&
      audioStart != null &&
      audioSize != null &&
      audioStart + audioSize <= bytes.length;
  if (!valid) {
    return const WavMetrics(
      durationSeconds: 0,
      rms: 0,
      peak: 0,
      trailingSilenceSeconds: 0,
      formatValid: false,
    );
  }

  final sampleCount = audioSize ~/ 2;
  var sumSquares = 0.0;
  var maximum = 0;
  for (var index = 0; index < sampleCount; index++) {
    final sample = data.getInt16(audioStart + index * 2, Endian.little);
    final absolute = sample.abs();
    if (absolute > maximum) {
      maximum = absolute;
    }
    final normalized = sample / 32768.0;
    sumSquares += normalized * normalized;
  }
  var trailingSilentSamples = 0;
  const silenceAmplitude = 0.01;
  for (var index = sampleCount - 1; index >= 0; index--) {
    final sample = data.getInt16(audioStart + index * 2, Endian.little);
    if (sample.abs() / 32768.0 > silenceAmplitude) {
      break;
    }
    trailingSilentSamples++;
  }

  return WavMetrics(
    durationSeconds: sampleCount / sampleRate!,
    rms: sampleCount == 0 ? 0 : math.sqrt(sumSquares / sampleCount),
    peak: maximum / 32768.0,
    trailingSilenceSeconds: trailingSilentSamples / sampleRate,
    formatValid: true,
  );
}

String _ascii(Uint8List bytes, int offset, int length) =>
    String.fromCharCodes(bytes, offset, offset + length);
