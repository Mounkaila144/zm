import 'package:corpus_recorder/app_controller.dart';
import 'package:corpus_recorder/models.dart';
import 'package:flutter_test/flutter_test.dart';

const _prompt = Prompt(id: 'x', zarmaText: 'afo', display: '1');

void main() {
  test('les seuils crête et RMS produisent une pastille rouge', () {
    final controller = AppController();
    final saturated = _speaker(
      Take(
        promptId: 'x',
        fileName: 'x.wav',
        recordedAt: _date,
        durationSeconds: 0.8,
        rms: 0.2,
        peak: 0.981,
        trailingSilenceSeconds: 0.2,
        formatValid: true,
      ),
    );
    controller.speakers.add(saturated);
    expect(controller.assess(saturated, _prompt).level, QualityLevel.bad);

    saturated.takes['x'] = Take(
      promptId: 'x',
      fileName: 'x.wav',
      recordedAt: _date,
      durationSeconds: 0.8,
      rms: 0.009,
      peak: 0.4,
      trailingSilenceSeconds: 0.2,
      formatValid: true,
    );
    expect(controller.assess(saturated, _prompt).level, QualityLevel.bad);
  });

  test('durée et silence final produisent une pastille orange', () {
    final controller = AppController();
    final speaker = _speaker(
      Take(
        promptId: 'x',
        fileName: 'x.wav',
        recordedAt: _date,
        durationSeconds: 0.3,
        rms: 0.1,
        peak: 0.4,
        trailingSilenceSeconds: 0.149,
        formatValid: true,
      ),
    );
    controller.speakers.add(speaker);

    final assessment = controller.assess(speaker, _prompt);
    expect(assessment.level, QualityLevel.warning);
    expect(assessment.reasons, hasLength(2));
  });

  test('une prise dans tous les seuils est verte', () {
    final controller = AppController();
    final speaker = _speaker(
      Take(
        promptId: 'x',
        fileName: 'x.wav',
        recordedAt: _date,
        durationSeconds: 0.8,
        rms: 0.1,
        peak: 0.4,
        trailingSilenceSeconds: 0.2,
        formatValid: true,
      ),
    );
    controller.speakers.add(speaker);

    expect(controller.assess(speaker, _prompt).level, QualityLevel.good);
  });
}

final _date = DateTime.utc(2026, 7, 30);

Speaker _speaker(Take take) => Speaker(
  name: 'Test',
  slug: 'test',
  code: 'abcd',
  listName: 'test',
  prompts: const <Prompt>[_prompt],
  takes: <String, Take>{'x': take},
);
