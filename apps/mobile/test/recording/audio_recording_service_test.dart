import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:record/record.dart';
import 'package:zarma_mobile/recording/audio_recording_models.dart';
import 'package:zarma_mobile/recording/audio_recording_service.dart';

class MockAudioRecorder extends Mock implements AudioRecorder {}

void main() {
  late Directory temporaryDirectory;

  setUpAll(() {
    registerFallbackValue(const RecordConfig());
  });

  setUp(() async {
    temporaryDirectory = await Directory.systemTemp.createTemp(
      'zarma_audio_test_',
    );
  });

  tearDown(() async {
    if (await temporaryDirectory.exists()) {
      await temporaryDirectory.delete(recursive: true);
    }
  });

  test('configure WAV PCM16 mono 16 kHz et un chemin temporaire unique',
      () async {
    final MockAudioRecorder recorder = MockAudioRecorder();
    when(() => recorder.cancel()).thenAnswer((_) async {});
    when(
      () => recorder.start(any(), path: any(named: 'path')),
    ).thenAnswer((_) async {});
    when(() => recorder.dispose()).thenAnswer((_) async {});
    final PluginAudioRecordingService service = PluginAudioRecordingService(
      recorder: recorder,
      temporaryDirectory: () async => temporaryDirectory,
      now: () => DateTime.fromMicrosecondsSinceEpoch(123456),
    );

    final String firstPath = await service.start();
    final String secondPath = await service.start();

    final List<dynamic> calls = verify(
      () => recorder.start(
        captureAny(),
        path: captureAny(named: 'path'),
      ),
    ).captured;
    final RecordConfig firstConfig = calls[0] as RecordConfig;
    expect(firstConfig.encoder, AudioEncoder.wav);
    expect(firstConfig.sampleRate, 16000);
    expect(firstConfig.numChannels, 1);
    expect(firstPath, endsWith('.wav'));
    expect(secondPath, isNot(firstPath));
    expect(firstPath, startsWith(temporaryDirectory.path));

    await service.dispose();
    await service.dispose();
    verify(() => recorder.dispose()).called(1);
  });

  test('inspecte un WAV PCM16 mono 16 kHz et mesure sa durée', () async {
    final File file = File('${temporaryDirectory.path}/valid.wav');
    await file.writeAsBytes(_wavBytes(duration: const Duration(seconds: 2)));

    final AudioFileInspection inspection = await inspectWavFile(file.path);

    expect(inspection.exists, isTrue);
    expect(inspection.isFormatValid, isTrue);
    expect(inspection.duration, const Duration(seconds: 2));
    expect(inspection.sizeBytes, await file.length());
  });

  test('refuse un format WAV non conforme', () async {
    final File file = File('${temporaryDirectory.path}/stereo.wav');
    await file.writeAsBytes(
      _wavBytes(duration: const Duration(seconds: 1), channels: 2),
    );

    final AudioFileInspection inspection = await inspectWavFile(file.path);

    expect(inspection.exists, isTrue);
    expect(inspection.isFormatValid, isFalse);
  });

  test('publie un nouveau flux de niveau pour chaque prise', () async {
    final MockAudioRecorder recorder = MockAudioRecorder();
    when(
      () => recorder.getAmplitude(),
    ).thenAnswer((_) async => Amplitude(current: -30, max: -20));
    final PluginAudioRecordingService service = PluginAudioRecordingService(
      recorder: recorder,
    );

    final double first = await service.amplitudeLevels().first;
    final double second = await service.amplitudeLevels().first;

    expect(first, 0.5);
    expect(second, 0.5);
    verify(() => recorder.getAmplitude()).called(2);
  });

  test('borne physiquement un WAV à dix secondes', () async {
    final File file = File('${temporaryDirectory.path}/too-long.wav');
    await file.writeAsBytes(
      _wavBytes(duration: const Duration(seconds: 11)),
    );

    await constrainWavDuration(file.path, const Duration(seconds: 10));
    final AudioFileInspection inspection = await inspectWavFile(file.path);

    expect(inspection.isFormatValid, isTrue);
    expect(inspection.duration, const Duration(seconds: 10));
    expect(inspection.sizeBytes, 320044);
  });

  test('supprime un temporaire et reste idempotent s’il est absent', () async {
    final MockAudioRecorder recorder = MockAudioRecorder();
    final PluginAudioRecordingService service = PluginAudioRecordingService(
      recorder: recorder,
    );
    final File file = File('${temporaryDirectory.path}/delete.wav');
    await file.writeAsBytes(<int>[1, 2, 3]);

    await service.deleteTemporary(file.path);
    await service.deleteTemporary(file.path);
    await service.deleteTemporary(null);

    expect(await file.exists(), isFalse);
  });
}

Uint8List _wavBytes({
  required Duration duration,
  int channels = 1,
  int sampleRate = 16000,
  int bitsPerSample = 16,
}) {
  final int blockAlign = channels * bitsPerSample ~/ 8;
  final int byteRate = sampleRate * blockAlign;
  final int dataSize =
      duration.inMicroseconds * byteRate ~/ Duration.microsecondsPerSecond;
  final Uint8List bytes = Uint8List(44 + dataSize);
  final ByteData data = ByteData.sublistView(bytes);

  _writeAscii(bytes, 0, 'RIFF');
  data.setUint32(4, 36 + dataSize, Endian.little);
  _writeAscii(bytes, 8, 'WAVE');
  _writeAscii(bytes, 12, 'fmt ');
  data.setUint32(16, 16, Endian.little);
  data.setUint16(20, 1, Endian.little);
  data.setUint16(22, channels, Endian.little);
  data.setUint32(24, sampleRate, Endian.little);
  data.setUint32(28, byteRate, Endian.little);
  data.setUint16(32, blockAlign, Endian.little);
  data.setUint16(34, bitsPerSample, Endian.little);
  _writeAscii(bytes, 36, 'data');
  data.setUint32(40, dataSize, Endian.little);
  return bytes;
}

void _writeAscii(Uint8List bytes, int offset, String value) {
  bytes.setRange(offset, offset + value.length, value.codeUnits);
}
