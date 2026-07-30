import 'models.dart';

List<List<String>> parseCsv(String source) {
  final rows = <List<String>>[];
  var row = <String>[];
  final field = StringBuffer();
  var quoted = false;

  void finishField() {
    row.add(field.toString());
    field.clear();
  }

  void finishRow() {
    finishField();
    if (row.any((value) => value.isNotEmpty)) {
      rows.add(row);
    }
    row = <String>[];
  }

  for (var index = 0; index < source.length; index++) {
    final character = source[index];
    if (quoted) {
      if (character == '"') {
        if (index + 1 < source.length && source[index + 1] == '"') {
          field.write('"');
          index++;
        } else {
          quoted = false;
        }
      } else {
        field.write(character);
      }
      continue;
    }
    if (character == '"' && field.isEmpty) {
      quoted = true;
    } else if (character == ',') {
      finishField();
    } else if (character == '\n') {
      finishRow();
    } else if (character != '\r') {
      field.write(character);
    }
  }
  if (quoted) {
    throw const FormatException('Guillemet CSV non fermé.');
  }
  if (field.isNotEmpty || row.isNotEmpty) {
    finishRow();
  }
  return rows;
}

List<Prompt> parsePromptsCsv(String source) {
  final rows = parseCsv(source);
  if (rows.isEmpty) {
    throw const FormatException('Le CSV est vide.');
  }
  if (rows.first.isNotEmpty) {
    rows.first[0] = rows.first[0].replaceFirst('\ufeff', '');
  }
  const expected = <String>['id', 'texte_zarma', 'affichage'];
  if (rows.first.length != expected.length ||
      List.generate(
        expected.length,
        (i) => rows.first[i].trim() == expected[i],
      ).contains(false)) {
    throw const FormatException('En-tête attendu : id,texte_zarma,affichage');
  }

  final prompts = <Prompt>[];
  final identifiers = <String>{};
  for (var index = 1; index < rows.length; index++) {
    final row = rows[index];
    if (row.length != 3) {
      throw FormatException('Ligne ${index + 1} : 3 colonnes attendues.');
    }
    final id = row[0].trim();
    final zarma = row[1].trim();
    final display = row[2].trim();
    if (id.isEmpty || zarma.isEmpty || display.isEmpty) {
      throw FormatException(
        'Ligne ${index + 1} : aucune valeur ne peut être vide.',
      );
    }
    if (RegExp(r'[\s\\\x00-\x1f]').hasMatch(id) || id == '.' || id == '..') {
      throw FormatException(
        'Ligne ${index + 1} : id invalide « $id » (espace, antislash ou contrôle).',
      );
    }
    if (!identifiers.add(id)) {
      throw FormatException('Ligne ${index + 1} : id « $id » en double.');
    }
    prompts.add(Prompt(id: id, zarmaText: zarma, display: display));
  }
  if (prompts.isEmpty) {
    throw const FormatException('Le CSV ne contient aucune consigne.');
  }
  return prompts;
}

String csvRow(Iterable<Object?> values) => values
    .map((value) {
      final text = value?.toString() ?? '';
      if (text.contains(',') || text.contains('"') || text.contains('\n')) {
        return '"${text.replaceAll('"', '""')}"';
      }
      return text;
    })
    .join(',');

/// `/` ne peut pas appartenir à un nom de fichier Android/ZIP à plat.
/// L'identifiant logique reste inchangé dans le manifest.
String fileNameForPrompt(String id) =>
    '${id.replaceAll('%', '%25').replaceAll('/', '%2F')}.wav';

String piperMetadataRow(String fileName, String zarmaText) {
  if (fileName.contains('|') ||
      zarmaText.contains('|') ||
      fileName.contains('\n') ||
      zarmaText.contains('\n')) {
    throw const FormatException(
      'Le format Piper interdit | et les retours à la ligne.',
    );
  }
  return '$fileName|$zarmaText';
}
