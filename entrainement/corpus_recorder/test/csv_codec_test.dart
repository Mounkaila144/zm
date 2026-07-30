import 'package:corpus_recorder/csv_codec.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('la liste embarquée contient les 32 consignes MVP exactes', () async {
    final source = await rootBundle.loadString('assets/consignes_mvp.csv');
    final prompts = parsePromptsCsv(source);

    expect(prompts, hasLength(32));
    expect(prompts.take(4).map((prompt) => prompt.id), <String>[
      'mot+',
      'mot-',
      'mot*',
      'mot/',
    ]);
    expect(prompts.where((prompt) => prompt.id.contains('/')), hasLength(8));
    expect(
      prompts.singleWhere((prompt) => prompt.id == '2+3').zarmaText,
      'ihinka kanga itonton ihinza',
    );
  });

  test('le parseur CSV accepte les champs protégés et refuse les doublons', () {
    final prompts = parsePromptsCsv(
      'id,texte_zarma,affichage\n'
      'x,"texte, avec virgule","sens, lisible"\n',
    );
    expect(prompts.single.zarmaText, 'texte, avec virgule');

    expect(
      () => parsePromptsCsv(
        'id,texte_zarma,affichage\n'
        'x,un,1\n'
        'x,deux,2\n',
      ),
      throwsFormatException,
    );
  });

  test('la barre oblique est échappée sans changer l’identifiant logique', () {
    expect(fileNameForPrompt('10/2'), '10%2F2.wav');
    expect(fileNameForPrompt('mot/'), 'mot%2F.wav');
    expect(fileNameForPrompt('2+3'), '2+3.wav');
  });
}
