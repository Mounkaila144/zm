import 'dart:io';
import 'dart:math' as math;
import 'dart:typed_data';

class WavMetrics {
  const WavMetrics({
    required this.durationSeconds,
    required this.rms,
    required this.peak,
    required this.leadingSilenceSeconds,
    required this.trailingSilenceSeconds,
    required this.noiseFloorRms,
    required this.dcOffset,
    required this.clippedFraction,
    required this.sampleRate,
    required this.pcmMono16,
    required this.formatValid,
  });

  const WavMetrics.invalid()
    : durationSeconds = 0,
      rms = 0,
      peak = 0,
      leadingSilenceSeconds = 0,
      trailingSilenceSeconds = 0,
      noiseFloorRms = 0,
      dcOffset = 0,
      clippedFraction = 0,
      sampleRate = 0,
      pcmMono16 = false,
      formatValid = false;

  final double durationSeconds;
  final double rms;
  final double peak;
  final double leadingSilenceSeconds;
  final double trailingSilenceSeconds;
  final double noiseFloorRms;
  final double dcOffset;
  final double clippedFraction;
  final int sampleRate;
  final bool pcmMono16;

  /// Master d'entraînement exigé : WAV PCM 48 kHz, mono, 16 bits.
  final bool formatValid;
}

Future<WavMetrics> inspectWav(String path) async {
  final bytes = await File(path).readAsBytes();
  if (bytes.length < 44 ||
      _ascii(bytes, 0, 4) != 'RIFF' ||
      _ascii(bytes, 8, 4) != 'WAVE') {
    return const WavMetrics.invalid();
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

  final pcmMono16 =
      format == 1 &&
      channels == 1 &&
      sampleRate != null &&
      sampleRate > 0 &&
      byteRate == sampleRate * 2 &&
      blockAlign == 2 &&
      bitsPerSample == 16 &&
      audioStart != null &&
      audioSize != null &&
      audioStart + audioSize <= bytes.length;
  if (!pcmMono16) {
    return const WavMetrics.invalid();
  }

  final sampleCount = audioSize ~/ 2;
  if (sampleCount == 0) {
    return const WavMetrics.invalid();
  }
  var sum = 0.0;
  var sumSquares = 0.0;
  var maximum = 0;
  var clippedSamples = 0;
  for (var index = 0; index < sampleCount; index++) {
    final sample = data.getInt16(audioStart + index * 2, Endian.little);
    final absolute = sample.abs();
    maximum = math.max(maximum, absolute);
    if (absolute / 32768.0 >= 0.98) {
      clippedSamples++;
    }
    final normalized = sample / 32768.0;
    sum += normalized;
    sumSquares += normalized * normalized;
  }

  const silenceAmplitude = 0.01;
  var leadingSilentSamples = 0;
  for (var index = 0; index < sampleCount; index++) {
    final sample = data.getInt16(audioStart + index * 2, Endian.little);
    if (sample.abs() / 32768.0 > silenceAmplitude) {
      break;
    }
    leadingSilentSamples++;
  }
  var trailingSilentSamples = 0;
  for (var index = sampleCount - 1; index >= 0; index--) {
    final sample = data.getInt16(audioStart + index * 2, Endian.little);
    if (sample.abs() / 32768.0 > silenceAmplitude) {
      break;
    }
    trailingSilentSamples++;
  }

  final noiseSamples = math.min(sampleCount, (sampleRate * 0.2).round());
  var noiseSquares = 0.0;
  for (var index = sampleCount - noiseSamples; index < sampleCount; index++) {
    final normalized =
        data.getInt16(audioStart + index * 2, Endian.little) / 32768.0;
    noiseSquares += normalized * normalized;
  }

  return WavMetrics(
    durationSeconds: sampleCount / sampleRate,
    rms: math.sqrt(sumSquares / sampleCount),
    peak: maximum / 32768.0,
    leadingSilenceSeconds: leadingSilentSamples / sampleRate,
    trailingSilenceSeconds: trailingSilentSamples / sampleRate,
    noiseFloorRms: math.sqrt(noiseSquares / noiseSamples),
    dcOffset: sum / sampleCount,
    clippedFraction: clippedSamples / sampleCount,
    sampleRate: sampleRate,
    pcmMono16: true,
    formatValid: sampleRate == 48000,
  );
}

String _ascii(Uint8List bytes, int offset, int length) =>
    String.fromCharCodes(bytes, offset, offset + length);
