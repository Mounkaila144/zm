import 'dart:math' as math;
import 'dart:typed_data';

Uint8List makePcmWav({
  required int sampleRate,
  double leadingSeconds = 0.1,
  double toneSeconds = 0.5,
  double trailingSeconds = 0.4,
  double amplitude = 0.4,
}) {
  final leading = (sampleRate * leadingSeconds).round();
  final tone = (sampleRate * toneSeconds).round();
  final trailing = (sampleRate * trailingSeconds).round();
  final sampleCount = leading + tone + trailing;
  final dataSize = sampleCount * 2;
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
  for (var index = 0; index < tone; index++) {
    final value =
        (math.sin(index * 2 * math.pi * 220 / sampleRate) * 32767 * amplitude)
            .round();
    data.setInt16(44 + (leading + index) * 2, value, Endian.little);
  }
  return bytes;
}

void _ascii(Uint8List bytes, int offset, String value) {
  bytes.setRange(offset, offset + value.length, value.codeUnits);
}
