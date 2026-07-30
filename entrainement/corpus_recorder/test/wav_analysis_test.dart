import 'dart:io';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:corpus_recorder/wav_analysis.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('inspecte un WAV PCM 16 kHz mono 16 bits sans le modifier', () async {
    final directory = await Directory.systemTemp.createTemp('corpus-wav-test-');
    addTearDown(() => directory.delete(recursive: true));
    final file = File('${directory.path}/test.wav');
    final bytes = _wavWithToneAndSilence();
    await file.writeAsBytes(bytes);

    final metrics = await inspectWav(file.path);

    expect(metrics.formatValid, isTrue);
    expect(metrics.durationSeconds, closeTo(1, 0.001));
    expect(metrics.trailingSilenceSeconds, closeTo(0.2, 0.001));
    expect(metrics.rms, greaterThan(0.01));
    expect(metrics.peak, closeTo(0.5, 0.01));
    expect(await file.readAsBytes(), bytes);
  });
}

Uint8List _wavWithToneAndSilence() {
  const sampleRate = 16000;
  const sampleCount = sampleRate;
  const dataSize = sampleCount * 2;
  final bytes = Uint8List(44 + dataSize);
  final data = ByteData.sublistView(bytes);
  _ascii(bytes, 0, 'RIFF');
  data.setUint32(4, bytes.length - 8, Endian.little);
  _ascii(bytes, 8, 'WAVE');
  _ascii(bytes, 12, 'fmt ');
  data
    ..setUint32(16, 16, Endian.little)
    ..setUint16(20, 1, Endian.little)
    ..setUint16(22, 1, Endian.little)
    ..setUint32(24, sampleRate, Endian.little)
    ..setUint32(28, sampleRate * 2, Endian.little)
    ..setUint16(32, 2, Endian.little)
    ..setUint16(34, 16, Endian.little);
  _ascii(bytes, 36, 'data');
  data.setUint32(40, dataSize, Endian.little);
  for (var index = 0; index < sampleRate * 0.8; index++) {
    final value = (math.sin(index * 2 * math.pi * 220 / sampleRate) * 16384)
        .round();
    data.setInt16(44 + index * 2, value, Endian.little);
  }
  return bytes;
}

void _ascii(Uint8List bytes, int offset, String value) {
  bytes.setRange(offset, offset + value.length, value.codeUnits);
}
