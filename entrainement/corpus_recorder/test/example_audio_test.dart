import 'dart:io';

import 'package:corpus_recorder/app_controller.dart';
import 'package:corpus_recorder/models.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  const prompt = Prompt(
    id: '2+3',
    zarmaText: 'ihinka kanga itonton ihinza',
    display: '2 + 3',
  );

  test('associe un manifest ZIP complet au CSV sélectionné', () async {
    final directory = await Directory.systemTemp.createTemp('zarma-example-');
    addTearDown(() => directory.delete(recursive: true));
    final file = File('${directory.path}/2+3.wav');
    final asset = await rootBundle.load('assets/examples/mvp/2+3.wav');
    await file.writeAsBytes(
      asset.buffer.asUint8List(asset.offsetInBytes, asset.lengthInBytes),
    );
    final controller = AppController()
      ..selectedPrompts = const <Prompt>[prompt];

    final count = await controller.useImportedExamples(
      manifest:
          'fichier,identifiant,texte_zarma,affichage,locuteur,code\n'
          '2+3.wav,2+3,ihinka kanga itonton ihinza,2 + 3,mounkaila,tksw\n',
      extractedFiles: <String, String>{'2+3.wav': file.path},
    );

    expect(count, 1);
    expect(controller.selectedExamplesComplete, isTrue);
    expect(controller.selectedExampleFiles['2+3'], file.path);
    expect(controller.selectedExampleSetName, 'Exemples · mounkaila-tksw');
  });

  test('refuse une étiquette zarma différente entre CSV et ZIP', () async {
    final controller = AppController()
      ..selectedPrompts = const <Prompt>[prompt];

    expect(
      () => controller.useImportedExamples(
        manifest:
            'fichier,identifiant,texte_zarma\n'
            '2+3.wav,2+3,etiquette fausse\n',
        extractedFiles: const <String, String>{
          '2+3.wav': '/chemin/inutile.wav',
        },
      ),
      throwsFormatException,
    );
  });

  test('conserve la banque d’exemples dans l’état du locuteur', () {
    final speaker = Speaker(
      name: 'Aïssata',
      slug: 'aissata',
      code: '7f3k',
      listName: 'MVP',
      prompts: const <Prompt>[prompt],
      exampleSetName: 'Exemples MVP',
      exampleAudio: const <String, String>{'2+3': '/audio/2+3.wav'},
    );

    final restored = Speaker.fromJson(speaker.toJson());

    expect(restored.exampleSetName, 'Exemples MVP');
    expect(restored.exampleAudio, <String, String>{'2+3': '/audio/2+3.wav'});
  });
}
