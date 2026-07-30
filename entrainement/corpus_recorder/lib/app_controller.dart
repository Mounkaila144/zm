import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:path_provider/path_provider.dart';

import 'csv_codec.dart';
import 'models.dart';
import 'wav_analysis.dart';
import 'zip_writer.dart';

class AppController extends ChangeNotifier {
  final List<Speaker> speakers = <Speaker>[];
  List<Prompt> selectedPrompts = <Prompt>[];
  String selectedListName = 'Liste MVP embarquée';
  Map<String, String> selectedExampleFiles = <String, String>{};
  String selectedExampleSetName = 'Exemples MVP · Mounkaila';
  Speaker? selectedSpeaker;
  bool initialized = false;

  late Directory _root;
  late Directory _recordings;
  late Directory _exports;
  late Directory _examples;
  late File _stateFile;

  bool get selectedExamplesComplete =>
      selectedPrompts.isNotEmpty &&
      selectedPrompts.every(
        (prompt) => selectedExampleFiles.containsKey(prompt.id),
      );

  Future<void> initialize() async {
    final documents = await getApplicationDocumentsDirectory();
    _root = Directory('${documents.path}/corpus_recorder');
    _recordings = Directory('${_root.path}/enregistrements');
    _exports = Directory('${_root.path}/exports');
    _examples = Directory('${_root.path}/exemples');
    _stateFile = File('${_root.path}/etat.json');
    await _recordings.create(recursive: true);
    await _exports.create(recursive: true);
    await _examples.create(recursive: true);

    final embedded = await rootBundle.loadString('assets/consignes_mvp.csv');
    selectedPrompts = parsePromptsCsv(embedded);
    selectedExampleFiles = await _installEmbeddedExamples(selectedPrompts);
    var stateChanged = false;
    if (await _stateFile.exists()) {
      try {
        final decoded =
            jsonDecode(await _stateFile.readAsString()) as Map<String, Object?>;
        final rawSpeakers =
            (decoded['locuteurs'] as List<Object?>?) ?? <Object?>[];
        speakers.addAll(
          rawSpeakers.map(
            (value) => Speaker.fromJson(value! as Map<String, Object?>),
          ),
        );
        for (final speaker in speakers) {
          if (speaker.exampleAudio.isEmpty &&
              _samePrompts(speaker.prompts, selectedPrompts)) {
            speaker
              ..exampleSetName = selectedExampleSetName
              ..exampleAudio = Map<String, String>.of(selectedExampleFiles);
            stateChanged = true;
          }
        }
      } on Object {
        final backup = File(
          '${_stateFile.path}.illisible-${DateTime.now().millisecondsSinceEpoch}',
        );
        await _stateFile.rename(backup.path);
      }
    }
    if (speakers.isNotEmpty) {
      selectedSpeaker = speakers.first;
    }
    if (stateChanged) {
      await save();
    }
    initialized = true;
    notifyListeners();
  }

  Future<void> useEmbeddedPrompts() async {
    final source = await rootBundle.loadString('assets/consignes_mvp.csv');
    selectedPrompts = parsePromptsCsv(source);
    selectedListName = 'Liste MVP embarquée';
    selectedExampleSetName = 'Exemples MVP · Mounkaila';
    selectedExampleFiles = await _installEmbeddedExamples(selectedPrompts);
    notifyListeners();
  }

  void useImportedPrompts(String csv) {
    selectedPrompts = parsePromptsCsv(csv);
    selectedListName = 'CSV importé (${selectedPrompts.length} consignes)';
    selectedExampleSetName = 'Aucun ZIP audio associé';
    selectedExampleFiles = <String, String>{};
    notifyListeners();
  }

  Future<Directory> prepareExampleImportDirectory() async {
    final directory = Directory(
      '${_examples.path}/importe-${DateTime.now().microsecondsSinceEpoch}',
    );
    await directory.create(recursive: true);
    return directory;
  }

  Future<void> discardExampleImport(Directory directory) async {
    if (await directory.exists()) {
      await directory.delete(recursive: true);
    }
  }

  Future<int> useImportedExamples({
    required String manifest,
    required Map<String, String> extractedFiles,
  }) async {
    final rows = parseCsv(manifest);
    if (rows.length < 2) {
      throw const FormatException('Le manifest du ZIP est vide.');
    }
    final headers = rows.first;
    final fileIndex = headers.indexOf('fichier');
    final idIndex = headers.indexOf('identifiant');
    final zarmaIndex = headers.indexOf('texte_zarma');
    final speakerIndex = headers.indexOf('locuteur');
    final codeIndex = headers.indexOf('code');
    if (fileIndex < 0 || idIndex < 0 || zarmaIndex < 0) {
      throw const FormatException(
        'Le manifest doit contenir fichier, identifiant et texte_zarma.',
      );
    }

    final expected = <String, Prompt>{
      for (final prompt in selectedPrompts) prompt.id: prompt,
    };
    final matched = <String, String>{};
    String? exampleSpeaker;
    String? exampleCode;
    for (var rowIndex = 1; rowIndex < rows.length; rowIndex++) {
      final row = rows[rowIndex];
      final requiredLength = max(fileIndex, max(idIndex, zarmaIndex)) + 1;
      if (row.length < requiredLength) {
        throw FormatException('Manifest, ligne ${rowIndex + 1} incomplète.');
      }
      final id = row[idIndex].trim();
      final prompt = expected[id];
      if (prompt == null) {
        throw FormatException(
          'Le ZIP contient « $id », absent du CSV sélectionné.',
        );
      }
      if (row[zarmaIndex].trim() != prompt.zarmaText) {
        throw FormatException(
          'Texte zarma différent pour « $id » entre le CSV et le ZIP.',
        );
      }
      final fileName = row[fileIndex].trim().split('/').last;
      final path = extractedFiles[fileName];
      if (path == null) {
        throw FormatException('Audio « $fileName » absent du ZIP.');
      }
      if (matched.containsKey(id)) {
        throw FormatException('Identifiant « $id » en double dans le ZIP.');
      }
      final metrics = await inspectWav(path);
      if (!metrics.formatValid) {
        throw FormatException(
          'Audio « $fileName » invalide : WAV PCM 16 kHz mono 16 bits requis.',
        );
      }
      matched[id] = path;
      if (speakerIndex >= 0 && speakerIndex < row.length) {
        exampleSpeaker ??= row[speakerIndex].trim();
      }
      if (codeIndex >= 0 && codeIndex < row.length) {
        exampleCode ??= row[codeIndex].trim();
      }
    }
    final missing = expected.keys
        .where((id) => !matched.containsKey(id))
        .toList();
    if (missing.isNotEmpty) {
      throw FormatException(
        '${missing.length} audio(s) manquant(s), dont « ${missing.first} ».',
      );
    }

    final labelParts = <String>[
      if (exampleSpeaker != null && exampleSpeaker.isNotEmpty) exampleSpeaker,
      if (exampleCode != null && exampleCode.isNotEmpty) exampleCode,
    ];
    selectedExampleSetName = labelParts.isEmpty
        ? 'ZIP audio importé (${matched.length} exemples)'
        : 'Exemples · ${labelParts.join('-')}';
    selectedExampleFiles = matched;
    notifyListeners();
    return matched.length;
  }

  Future<Speaker> addSpeaker(String rawName) async {
    final name = rawName.trim();
    if (name.isEmpty) {
      throw const FormatException('Saisissez un prénom ou un surnom.');
    }
    var slug = _slugify(name);
    if (slug.isEmpty) {
      slug = 'locuteur';
    }
    final existingCodes = speakers.map((speaker) => speaker.code).toSet();
    final random = Random.secure();
    const alphabet = 'abcdefghjkmnpqrstuvwxyz23456789';
    String code;
    do {
      code = List.generate(
        4,
        (_) => alphabet[random.nextInt(alphabet.length)],
      ).join();
    } while (existingCodes.contains(code));
    final prompts = _shuffled(selectedPrompts, code);
    final speaker = Speaker(
      name: name,
      slug: slug,
      code: code,
      listName: selectedListName,
      prompts: prompts,
      exampleSetName: selectedExampleSetName,
      exampleAudio: Map<String, String>.of(selectedExampleFiles),
    );
    speakers.add(speaker);
    selectedSpeaker = speaker;
    await save();
    notifyListeners();
    return speaker;
  }

  void selectSpeaker(Speaker speaker) {
    selectedSpeaker = speaker;
    notifyListeners();
  }

  Future<void> restartSpeaker(Speaker speaker) async {
    final directory = speakerDirectory(speaker);
    if (await directory.exists()) {
      await directory.delete(recursive: true);
    }
    speaker
      ..takes.clear()
      ..prompts = _shuffled(selectedPrompts, speaker.code)
      ..listName = selectedListName
      ..exampleSetName = selectedExampleSetName
      ..exampleAudio = Map<String, String>.of(selectedExampleFiles)
      ..currentIndex = 0;
    await save();
    notifyListeners();
  }

  Directory speakerDirectory(Speaker speaker) =>
      Directory('${_recordings.path}/${speaker.folderName}');

  File takeFile(Speaker speaker, Take take) =>
      File('${speakerDirectory(speaker).path}/${take.fileName}');

  String? examplePath(Speaker speaker, Prompt prompt) =>
      speaker.exampleAudio[prompt.id];

  Future<Take> storeTake({
    required Speaker speaker,
    required Prompt prompt,
    required String temporaryPath,
    required bool autoStopped,
  }) async {
    final metrics = await inspectWav(temporaryPath);
    if (!metrics.formatValid) {
      final invalid = File(temporaryPath);
      if (await invalid.exists()) {
        await invalid.delete();
      }
      throw const FormatException(
        'Le téléphone n’a pas produit un WAV PCM 16 kHz mono 16 bits.',
      );
    }
    final directory = speakerDirectory(speaker);
    await directory.create(recursive: true);
    final fileName = fileNameForPrompt(prompt.id);
    final destination = File('${directory.path}/$fileName');
    final source = File(temporaryPath);
    final replacement = File('${destination.path}.nouveau');
    if (await replacement.exists()) {
      await replacement.delete();
    }
    await source.rename(replacement.path);
    if (await destination.exists()) {
      await destination.delete();
    }
    await replacement.rename(destination.path);
    final take = Take(
      promptId: prompt.id,
      fileName: fileName,
      recordedAt: DateTime.now().toUtc(),
      durationSeconds: metrics.durationSeconds,
      rms: metrics.rms,
      peak: metrics.peak,
      trailingSilenceSeconds: metrics.trailingSilenceSeconds,
      formatValid: metrics.formatValid,
      autoStopped: autoStopped,
    );
    speaker.takes[prompt.id] = take;
    await save();
    notifyListeners();
    return take;
  }

  QualityAssessment assess(Speaker speaker, Prompt prompt) {
    final take = speaker.takes[prompt.id];
    if (take == null) {
      return const QualityAssessment(QualityLevel.missing, <String>[
        'Prise manquante',
      ]);
    }
    final bad = <String>[];
    final warnings = <String>[];
    if (!take.formatValid) {
      bad.add('Format audio invalide');
    }
    if (take.peak > 0.98) {
      bad.add('Saturation (crête > 0,98)');
    }
    if (take.rms < 0.01) {
      bad.add('Niveau trop faible (RMS < 0,01)');
    }
    final median = expectedMedian(prompt.wordCount);
    if (take.durationSeconds < median * 0.45 ||
        take.durationSeconds > median * 2.2) {
      warnings.add(
        'Durée inhabituelle (${take.durationSeconds.toStringAsFixed(2)} s, '
        'attendu ≈ ${median.toStringAsFixed(2)} s)',
      );
    }
    if (take.trailingSilenceSeconds < 0.15) {
      warnings.add('Moins de 150 ms de silence final');
    }
    if (take.autoStopped) {
      warnings.add('Arrêt automatique à 15 s');
    }
    if (bad.isNotEmpty) {
      return QualityAssessment(QualityLevel.bad, <String>[...bad, ...warnings]);
    }
    if (warnings.isNotEmpty) {
      return QualityAssessment(QualityLevel.warning, warnings);
    }
    return const QualityAssessment(QualityLevel.good, <String>[]);
  }

  double expectedMedian(int wordCount) {
    final durations = <double>[];
    for (final speaker in speakers) {
      for (final prompt in speaker.prompts) {
        final take = speaker.takes[prompt.id];
        if (prompt.wordCount == wordCount &&
            take != null &&
            take.formatValid &&
            take.rms >= 0.01 &&
            take.peak <= 0.98) {
          durations.add(take.durationSeconds);
        }
      }
    }
    if (durations.length >= 3) {
      durations.sort();
      final middle = durations.length ~/ 2;
      return durations.length.isOdd
          ? durations[middle]
          : (durations[middle - 1] + durations[middle]) / 2;
    }
    return 0.45 + 0.35 * wordCount;
  }

  Future<void> save() async {
    final payload = jsonEncode(<String, Object?>{
      'version': 2,
      'locuteurs': speakers.map((speaker) => speaker.toJson()).toList(),
    });
    final temporary = File('${_stateFile.path}.nouveau');
    await temporary.writeAsString(payload, flush: true);
    if (await _stateFile.exists()) {
      await _stateFile.delete();
    }
    await temporary.rename(_stateFile.path);
  }

  Future<File> exportSpeaker(Speaker speaker) async {
    final file = File('${_exports.path}/${speaker.folderName}.zip');
    return _export(file, <Speaker>[speaker]);
  }

  Future<File> exportAll() async {
    final now = DateTime.now();
    final date =
        '${now.year.toString().padLeft(4, '0')}-'
        '${now.month.toString().padLeft(2, '0')}-'
        '${now.day.toString().padLeft(2, '0')}';
    final file = File('${_exports.path}/zarma_corpus_$date.zip');
    return _export(
      file,
      speakers.where((speaker) => speaker.takes.isNotEmpty).toList(),
    );
  }

  Future<File> _export(File destination, List<Speaker> included) async {
    final entries = <ZipEntrySource>[];
    for (final speaker in included) {
      final base = 'zarma_corpus/${speaker.folderName}';
      final manifest = StringBuffer()
        ..writeln(
          csvRow(<String>[
            'fichier',
            'identifiant',
            'texte_zarma',
            'affichage',
            'locuteur',
            'code',
            'date',
            'duree_s',
            'rms',
            'crete',
            'qualite',
          ]),
        );
      for (final prompt in speaker.prompts) {
        final take = speaker.takes[prompt.id];
        if (take == null) {
          continue;
        }
        final file = takeFile(speaker, take);
        if (!await file.exists()) {
          continue;
        }
        manifest.writeln(
          csvRow(<Object>[
            take.fileName,
            prompt.id,
            prompt.zarmaText,
            prompt.display,
            speaker.slug,
            speaker.code,
            take.recordedAt.toUtc().toIso8601String(),
            take.durationSeconds.toStringAsFixed(3),
            take.rms.toStringAsFixed(5),
            take.peak.toStringAsFixed(5),
            assess(speaker, prompt).manifestValue,
          ]),
        );
        entries.add(ZipEntrySource.fromFile('$base/${take.fileName}', file));
      }
      entries.add(
        ZipEntrySource.fromBytes(
          '$base/manifest.csv',
          Uint8List.fromList(utf8.encode(manifest.toString())),
        ),
      );
    }
    return writeStoredZip(destination, entries);
  }

  Future<Map<String, String>> _installEmbeddedExamples(
    List<Prompt> prompts,
  ) async {
    final directory = Directory('${_examples.path}/mvp-mounkaila-v1');
    await directory.create(recursive: true);
    final installed = <String, String>{};
    for (final prompt in prompts) {
      final fileName = fileNameForPrompt(prompt.id);
      final data = await rootBundle.load('assets/examples/mvp/$fileName');
      final bytes = data.buffer.asUint8List(
        data.offsetInBytes,
        data.lengthInBytes,
      );
      final file = File('${directory.path}/$fileName');
      if (!await file.exists() || await file.length() != bytes.length) {
        await file.writeAsBytes(bytes, flush: true);
      }
      installed[prompt.id] = file.path;
    }
    return installed;
  }

  static bool _samePrompts(List<Prompt> left, List<Prompt> right) {
    if (left.length != right.length) {
      return false;
    }
    final rightById = <String, Prompt>{
      for (final prompt in right) prompt.id: prompt,
    };
    return left.every((prompt) {
      final other = rightById[prompt.id];
      return other != null &&
          other.zarmaText == prompt.zarmaText &&
          other.display == prompt.display;
    });
  }

  static String _slugify(String input) {
    const replacements = <String, String>{
      'à': 'a',
      'á': 'a',
      'â': 'a',
      'ä': 'a',
      'ã': 'a',
      'å': 'a',
      'ç': 'c',
      'è': 'e',
      'é': 'e',
      'ê': 'e',
      'ë': 'e',
      'ì': 'i',
      'í': 'i',
      'î': 'i',
      'ï': 'i',
      'ñ': 'n',
      'ò': 'o',
      'ó': 'o',
      'ô': 'o',
      'ö': 'o',
      'õ': 'o',
      'ù': 'u',
      'ú': 'u',
      'û': 'u',
      'ü': 'u',
      'ý': 'y',
      'ÿ': 'y',
    };
    var value = input.toLowerCase();
    replacements.forEach((source, target) {
      value = value.replaceAll(source, target);
    });
    return value
        .replaceAll(RegExp('[^a-z0-9]+'), '-')
        .replaceAll(RegExp('^-+|-+\$'), '');
  }

  static List<Prompt> _shuffled(List<Prompt> source, String code) {
    var seed = 0x811c9dc5;
    for (final byte in utf8.encode(code)) {
      seed ^= byte;
      seed = (seed * 0x01000193) & 0x7fffffff;
    }
    final prompts = List<Prompt>.of(source);
    prompts.shuffle(Random(seed));
    return prompts;
  }
}
