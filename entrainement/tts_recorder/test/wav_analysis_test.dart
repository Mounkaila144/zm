import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:tts_recorder/wav_analysis.dart';

import 'support/wav_factory.dart';

void main() {
  test('valide et mesure un master PCM 48 kHz mono 16 bits', () async {
    final directory = await Directory.systemTemp.createTemp('tts-wav-');
    addTearDown(() => directory.delete(recursive: true));
    final file = File('${directory.path}/master.wav');
    final bytes = makePcmWav(sampleRate: 48000);
    await file.writeAsBytes(bytes);

    final metrics = await inspectWav(file.path);

    expect(metrics.formatValid, isTrue);
    expect(metrics.pcmMono16, isTrue);
    expect(metrics.sampleRate, 48000);
    expect(metrics.durationSeconds, closeTo(1, 0.001));
    expect(metrics.leadingSilenceSeconds, closeTo(0.1, 0.001));
    expect(metrics.trailingSilenceSeconds, closeTo(0.4, 0.001));
    expect(metrics.peak, closeTo(0.4, 0.01));
    expect(metrics.noiseFloorRms, 0);
    expect(await file.readAsBytes(), bytes);
  });

  test('reconnaît un exemple 16 kHz mais le refuse comme master TTS', () async {
    final directory = await Directory.systemTemp.createTemp('tts-wav-');
    addTearDown(() => directory.delete(recursive: true));
    final file = File('${directory.path}/example.wav');
    await file.writeAsBytes(makePcmWav(sampleRate: 16000));

    final metrics = await inspectWav(file.path);

    expect(metrics.pcmMono16, isTrue);
    expect(metrics.sampleRate, 16000);
    expect(metrics.formatValid, isFalse);
  });
}
