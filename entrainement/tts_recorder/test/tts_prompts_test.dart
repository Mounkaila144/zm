import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:tts_recorder/csv_codec.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test(
    'le vocabulaire fermé contient exactement 400 consignes uniques',
    () async {
      final source = await rootBundle.loadString('assets/tts_prompts.csv');
      final prompts = parsePromptsCsv(source);

      expect(prompts, hasLength(400));
      expect(prompts.map((prompt) => prompt.id).toSet(), hasLength(400));
      expect(prompts.map((prompt) => prompt.zarmaText).toSet(), hasLength(400));
      expect(
        prompts
            .map((prompt) => prompt.wordCount)
            .reduce((a, b) => a < b ? a : b),
        1,
      );
      expect(
        prompts
            .map((prompt) => prompt.wordCount)
            .reduce((a, b) => a > b ? a : b),
        17,
      );
      expect(prompts.any((prompt) => prompt.zarmaText.contains('|')), isFalse);
    },
  );

  test('échappe les divisions dans les noms et produit une ligne Piper', () {
    expect(fileNameForPrompt('tts_1/5'), 'tts_1%2F5.wav');
    expect(
      piperMetadataRow('tts_1%2F5.wav', 'afo inafaysor igou'),
      'tts_1%2F5.wav|afo inafaysor igou',
    );
    expect(
      () => piperMetadataRow('x.wav', 'texte|interdit'),
      throwsFormatException,
    );
  });
}
