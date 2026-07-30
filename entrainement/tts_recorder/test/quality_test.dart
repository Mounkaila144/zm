import 'package:flutter_test/flutter_test.dart';
import 'package:tts_recorder/app_controller.dart';
import 'package:tts_recorder/models.dart';

const prompt = Prompt(id: 'tts_1', zarmaText: 'afo', display: '1');
final date = DateTime.utc(2026, 7, 30);

void main() {
  test('une prise TTS propre est verte', () {
    final controller = AppController();
    final speaker = _speaker(_take());
    controller.speakers.add(speaker);

    expect(controller.assess(speaker, prompt).level, QualityLevel.good);
  });

  test('la saturation rend la prise inutilisable', () {
    final controller = AppController();
    final speaker = _speaker(_take(peak: 0.98, clippedFraction: 0.0001));
    controller.speakers.add(speaker);

    expect(controller.assess(speaker, prompt).level, QualityLevel.bad);
  });

  test('un bruit de fond élevé rend la prise douteuse', () {
    final controller = AppController();
    final speaker = _speaker(_take(noiseFloorRms: 0.021));
    controller.speakers.add(speaker);

    expect(controller.assess(speaker, prompt).level, QualityLevel.warning);
  });
}

Take _take({
  double peak = 0.5,
  double clippedFraction = 0,
  double noiseFloorRms = 0.005,
}) => Take(
  promptId: prompt.id,
  fileName: 'tts_1.wav',
  recordedAt: date,
  durationSeconds: 0.85,
  rms: 0.08,
  peak: peak,
  leadingSilenceSeconds: 0.1,
  trailingSilenceSeconds: 0.3,
  noiseFloorRms: noiseFloorRms,
  dcOffset: 0,
  clippedFraction: clippedFraction,
  formatValid: true,
);

Speaker _speaker(Take take) => Speaker(
  name: 'Voix',
  slug: 'voix',
  code: 'abcd',
  listName: 'TTS',
  prompts: const <Prompt>[prompt],
  takes: <String, Take>{prompt.id: take},
);
