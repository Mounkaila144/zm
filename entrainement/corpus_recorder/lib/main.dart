import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:share_plus/share_plus.dart';

import 'app_controller.dart';
import 'audio_service.dart';
import 'models.dart';
import 'platform_bridge.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final controller = AppController();
  await controller.initialize();
  runApp(CorpusRecorderApp(controller: controller));
}

class CorpusRecorderApp extends StatefulWidget {
  const CorpusRecorderApp({super.key, required this.controller});

  final AppController controller;

  @override
  State<CorpusRecorderApp> createState() => _CorpusRecorderAppState();
}

class _CorpusRecorderAppState extends State<CorpusRecorderApp> {
  final AudioCaptureService audio = AudioCaptureService();
  final PlatformBridge platform = PlatformBridge();

  @override
  void dispose() {
    unawaited(audio.dispose());
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    const seed = Color(0xff176b52);
    return MaterialApp(
      title: 'Corpus vocal zarma',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: seed,
          brightness: Brightness.light,
        ),
        useMaterial3: true,
        scaffoldBackgroundColor: const Color(0xfff7f7f2),
        appBarTheme: const AppBarTheme(
          backgroundColor: Color(0xfff7f7f2),
          surfaceTintColor: Colors.transparent,
        ),
        filledButtonTheme: FilledButtonThemeData(
          style: FilledButton.styleFrom(
            minimumSize: const Size(0, 52),
            textStyle: const TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.w700,
            ),
          ),
        ),
      ),
      home: SessionScreen(
        controller: widget.controller,
        audio: audio,
        platform: platform,
      ),
    );
  }
}

class SessionScreen extends StatelessWidget {
  const SessionScreen({
    super.key,
    required this.controller,
    required this.audio,
    required this.platform,
  });

  final AppController controller;
  final AudioCaptureService audio;
  final PlatformBridge platform;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        final speaker = controller.selectedSpeaker;
        return Scaffold(
          appBar: AppBar(title: const Text('Nouvelle séance')),
          body: SafeArea(
            child: ListView(
              padding: const EdgeInsets.fromLTRB(20, 8, 20, 28),
              children: <Widget>[
                const _IntroCard(),
                const SizedBox(height: 24),
                Text(
                  '1. Locuteur',
                  style: Theme.of(
                    context,
                  ).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800),
                ),
                const SizedBox(height: 10),
                if (controller.speakers.isEmpty)
                  const Text('Aucun locuteur sur ce téléphone.')
                else
                  DropdownButtonFormField<Speaker>(
                    initialValue: speaker,
                    decoration: const InputDecoration(
                      border: OutlineInputBorder(),
                      labelText: 'Choisir un locuteur',
                    ),
                    items: controller.speakers
                        .map(
                          (item) => DropdownMenuItem(
                            value: item,
                            child: Text('${item.name} · ${item.code}'),
                          ),
                        )
                        .toList(),
                    onChanged: (value) {
                      if (value != null) {
                        controller.selectSpeaker(value);
                      }
                    },
                  ),
                const SizedBox(height: 10),
                OutlinedButton.icon(
                  onPressed: () => _createSpeaker(context),
                  icon: const Icon(Icons.person_add_alt_1),
                  label: const Text('Créer un nouveau locuteur'),
                ),
                if (speaker != null) ...<Widget>[
                  const SizedBox(height: 10),
                  _SpeakerStatus(speaker: speaker),
                ],
                const SizedBox(height: 28),
                Text(
                  '2. Liste de consignes',
                  style: Theme.of(
                    context,
                  ).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800),
                ),
                const SizedBox(height: 10),
                Card(
                  margin: EdgeInsets.zero,
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: <Widget>[
                        Text(
                          controller.selectedListName,
                          style: const TextStyle(fontWeight: FontWeight.w700),
                        ),
                        const SizedBox(height: 4),
                        Text('${controller.selectedPrompts.length} consignes'),
                        const SizedBox(height: 14),
                        OutlinedButton.icon(
                          onPressed: () async {
                            await controller.useEmbeddedPrompts();
                            if (context.mounted) {
                              _message(
                                context,
                                'Liste MVP embarquée sélectionnée.',
                              );
                            }
                          },
                          icon: const Icon(Icons.offline_pin_outlined),
                          label: const Text('Utiliser la liste embarquée'),
                        ),
                        OutlinedButton.icon(
                          onPressed: () => _importCsv(context),
                          icon: const Icon(Icons.file_open_outlined),
                          label: const Text('Importer un CSV'),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 28),
                Text(
                  '3. Audios d’exemple',
                  style: Theme.of(
                    context,
                  ).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800),
                ),
                const SizedBox(height: 10),
                Card(
                  margin: EdgeInsets.zero,
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: <Widget>[
                        Row(
                          children: <Widget>[
                            Icon(
                              controller.selectedExamplesComplete
                                  ? Icons.check_circle
                                  : Icons.warning_amber_rounded,
                              color: controller.selectedExamplesComplete
                                  ? qualityColor(QualityLevel.good)
                                  : qualityColor(QualityLevel.warning),
                            ),
                            const SizedBox(width: 10),
                            Expanded(
                              child: Text(
                                controller.selectedExampleSetName,
                                style: const TextStyle(
                                  fontWeight: FontWeight.w700,
                                ),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 6),
                        Text(
                          '${controller.selectedExampleFiles.length} / '
                          '${controller.selectedPrompts.length} exemples associés',
                        ),
                        const SizedBox(height: 14),
                        OutlinedButton.icon(
                          onPressed: () => _importExampleZip(context),
                          icon: const Icon(Icons.folder_zip_outlined),
                          label: const Text('Importer le ZIP des audios'),
                        ),
                        const Text(
                          'Le CSV et le manifest du ZIP doivent avoir exactement '
                          'les mêmes identifiants et textes zarma.',
                          style: TextStyle(color: Colors.black54, fontSize: 12),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 28),
                FilledButton.icon(
                  onPressed: speaker == null
                      ? null
                      : () => _start(context, speaker),
                  icon: const Icon(Icons.mic),
                  label: Text(
                    speaker?.hasStarted == true
                        ? 'Ouvrir la séance'
                        : 'Commencer',
                  ),
                ),
                if (speaker?.hasStarted == true) ...<Widget>[
                  const SizedBox(height: 8),
                  TextButton.icon(
                    onPressed: () => _openReview(context, speaker!),
                    icon: const Icon(Icons.fact_check_outlined),
                    label: const Text('Revue et export'),
                  ),
                ],
              ],
            ),
          ),
        );
      },
    );
  }

  Future<void> _createSpeaker(BuildContext context) async {
    final textController = TextEditingController();
    final name = await showDialog<String>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Nouveau locuteur'),
        content: TextField(
          controller: textController,
          autofocus: true,
          textCapitalization: TextCapitalization.words,
          decoration: const InputDecoration(
            labelText: 'Prénom ou surnom',
            hintText: 'Ex. Aïssata',
          ),
          onSubmitted: (value) => Navigator.pop(dialogContext, value),
        ),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.pop(dialogContext),
            child: const Text('Annuler'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialogContext, textController.text),
            child: const Text('Créer'),
          ),
        ],
      ),
    );
    textController.dispose();
    if (name == null || !context.mounted) {
      return;
    }
    try {
      final speaker = await controller.addSpeaker(name);
      if (context.mounted) {
        _message(context, 'Code unique créé : ${speaker.folderName}');
      }
    } on FormatException catch (error) {
      if (context.mounted) {
        _message(context, error.message, error: true);
      }
    }
  }

  Future<void> _importCsv(BuildContext context) async {
    try {
      final csv = await platform.importCsv();
      if (csv == null) {
        return;
      }
      controller.useImportedPrompts(csv);
      if (context.mounted) {
        _message(
          context,
          '${controller.selectedPrompts.length} consignes importées.',
        );
      }
    } on Object catch (error) {
      if (context.mounted) {
        _message(context, 'CSV refusé : $error', error: true);
      }
    }
  }

  Future<void> _importExampleZip(BuildContext context) async {
    Directory? importDirectory;
    try {
      importDirectory = await controller.prepareExampleImportDirectory();
      final imported = await platform.importExampleZip(importDirectory.path);
      if (imported == null) {
        await controller.discardExampleImport(importDirectory);
        return;
      }
      final count = await controller.useImportedExamples(
        manifest: imported.manifest,
        extractedFiles: imported.files,
      );
      if (context.mounted) {
        _message(context, '$count audios d’exemple associés au CSV.');
      }
    } on Object catch (error) {
      if (importDirectory != null) {
        await controller.discardExampleImport(importDirectory);
      }
      if (context.mounted) {
        _message(context, 'ZIP audio refusé : $error', error: true);
      }
    }
  }

  Future<void> _start(BuildContext context, Speaker speaker) async {
    if (speaker.hasStarted) {
      final action = await showDialog<_ResumeAction>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          title: Text('Séance de ${speaker.name}'),
          content: Text(
            '${speaker.takes.length} prise(s) sur ${speaker.prompts.length}. '
            'Voulez-vous reprendre ou effacer cette séance et recommencer ?',
          ),
          actions: <Widget>[
            TextButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: const Text('Annuler'),
            ),
            TextButton(
              onPressed: () =>
                  Navigator.pop(dialogContext, _ResumeAction.restart),
              child: const Text('Recommencer'),
            ),
            FilledButton(
              onPressed: () =>
                  Navigator.pop(dialogContext, _ResumeAction.resume),
              child: const Text('Reprendre'),
            ),
          ],
        ),
      );
      if (action == null || !context.mounted) {
        return;
      }
      if (action == _ResumeAction.restart) {
        if (!controller.selectedExamplesComplete) {
          _message(
            context,
            'Importez d’abord un ZIP audio complet pour recommencer.',
            error: true,
          );
          return;
        }
        final confirmed = await showDialog<bool>(
          context: context,
          builder: (dialogContext) => AlertDialog(
            title: const Text('Effacer les prises ?'),
            content: const Text(
              'Les fichiers audio de ce locuteur seront supprimés du téléphone.',
            ),
            actions: <Widget>[
              TextButton(
                onPressed: () => Navigator.pop(dialogContext, false),
                child: const Text('Garder'),
              ),
              FilledButton(
                onPressed: () => Navigator.pop(dialogContext, true),
                child: const Text('Effacer et recommencer'),
              ),
            ],
          ),
        );
        if (confirmed != true) {
          return;
        }
        await controller.restartSpeaker(speaker);
      } else if (!speaker.prompts.every(
        (prompt) => speaker.exampleAudio.containsKey(prompt.id),
      )) {
        _message(
          context,
          'Cette séance n’a pas tous ses exemples audio. '
          'Sélectionnez le CSV et son ZIP, puis recommencez la séance.',
          error: true,
        );
        return;
      }
    } else {
      if (!controller.selectedExamplesComplete) {
        _message(
          context,
          'Importez le ZIP des audios avant de commencer.',
          error: true,
        );
        return;
      }
      // La liste est choisie après le locuteur à l'écran : l'appliquer au
      // dernier moment garantit que le choix visible est celui de la séance.
      await controller.restartSpeaker(speaker);
    }
    if (!context.mounted) {
      return;
    }
    await Navigator.push(
      context,
      MaterialPageRoute<void>(
        builder: (_) => RecordingScreen(
          controller: controller,
          audio: audio,
          platform: platform,
          speaker: speaker,
          initialIndex: speaker.currentIndex.clamp(
            0,
            speaker.prompts.length - 1,
          ),
        ),
      ),
    );
  }

  Future<void> _openReview(BuildContext context, Speaker speaker) =>
      Navigator.push(
        context,
        MaterialPageRoute<void>(
          builder: (_) => ReviewScreen(
            controller: controller,
            audio: audio,
            platform: platform,
            speaker: speaker,
          ),
        ),
      );
}

enum _ResumeAction { resume, restart }

class _IntroCard extends StatelessWidget {
  const _IntroCard();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.primaryContainer,
        borderRadius: BorderRadius.circular(18),
      ),
      child: const Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Icon(Icons.signal_wifi_off),
          SizedBox(width: 12),
          Expanded(
            child: Text(
              'Tout fonctionne hors-ligne. Enregistrez dans un endroit calme, '
              'puis envoyez le ZIP quand une connexion est disponible.',
            ),
          ),
        ],
      ),
    );
  }
}

class _SpeakerStatus extends StatelessWidget {
  const _SpeakerStatus({required this.speaker});

  final Speaker speaker;

  @override
  Widget build(BuildContext context) {
    final progress = speaker.prompts.isEmpty
        ? 0.0
        : speaker.takes.length / speaker.prompts.length;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Text(
          '${speaker.folderName} · liste : ${speaker.listName}',
          style: Theme.of(context).textTheme.bodySmall,
        ),
        Text(
          speaker.exampleSetName.isEmpty
              ? 'Exemples audio : absents'
              : 'Exemples audio : ${speaker.exampleSetName}',
          style: Theme.of(context).textTheme.bodySmall,
        ),
        const SizedBox(height: 6),
        LinearProgressIndicator(value: progress),
        const SizedBox(height: 4),
        Text('${speaker.takes.length} / ${speaker.prompts.length} prises'),
      ],
    );
  }
}

class RecordingScreen extends StatefulWidget {
  const RecordingScreen({
    super.key,
    required this.controller,
    required this.audio,
    required this.platform,
    required this.speaker,
    required this.initialIndex,
  });

  final AppController controller;
  final AudioCaptureService audio;
  final PlatformBridge platform;
  final Speaker speaker;
  final int initialIndex;

  @override
  State<RecordingScreen> createState() => _RecordingScreenState();
}

class _RecordingScreenState extends State<RecordingScreen> {
  late int index;
  bool pointerHeld = false;
  bool preparing = false;
  bool recording = false;
  bool finishing = false;
  DateTime? startedAt;
  Timer? maximumTimer;

  Speaker get speaker => widget.speaker;
  Prompt get prompt => speaker.prompts[index];
  Take? get take => speaker.takes[prompt.id];
  String? get examplePath => widget.controller.examplePath(speaker, prompt);

  @override
  void initState() {
    super.initState();
    index = widget.initialIndex;
  }

  @override
  void dispose() {
    maximumTimer?.cancel();
    if (recording || preparing) {
      unawaited(widget.audio.cancel());
    }
    super.dispose();
  }

  Future<void> _press() async {
    if (recording || preparing || finishing) {
      return;
    }
    pointerHeld = true;
    preparing = true;
    HapticFeedback.selectionClick();
    setState(() {});
    try {
      await widget.platform.stopPlayback();
      await widget.audio.start();
      if (!mounted || !pointerHeld) {
        await widget.audio.cancel();
        if (mounted) {
          setState(() => preparing = false);
        }
        return;
      }
      startedAt = DateTime.now();
      preparing = false;
      recording = true;
      maximumTimer = Timer(
        const Duration(seconds: 15),
        () => _finish(autoStopped: true, addPostRoll: false),
      );
      setState(() {});
    } on MicrophonePermissionException {
      if (mounted) {
        setState(() => preparing = false);
        _message(
          context,
          'Autorisez le microphone dans les réglages Android.',
          error: true,
        );
      }
    } on Object catch (error) {
      if (mounted) {
        setState(() => preparing = false);
        _message(context, 'Enregistrement impossible : $error', error: true);
      }
    }
  }

  Future<void> _release() async {
    pointerHeld = false;
    HapticFeedback.selectionClick();
    if (!recording || finishing) {
      return;
    }
    final elapsed = DateTime.now().difference(startedAt!);
    if (elapsed < const Duration(milliseconds: 300)) {
      maximumTimer?.cancel();
      recording = false;
      await widget.audio.cancel();
      if (mounted) {
        setState(() {});
        _message(context, 'Appui trop court : aucune prise enregistrée.');
      }
      return;
    }
    await _finish(autoStopped: false, addPostRoll: true);
  }

  Future<void> _finish({
    required bool autoStopped,
    required bool addPostRoll,
  }) async {
    if (!recording || finishing) {
      return;
    }
    finishing = true;
    pointerHeld = false;
    maximumTimer?.cancel();
    setState(() {});
    if (addPostRoll) {
      await Future<void>.delayed(const Duration(milliseconds: 400));
    }
    try {
      final path = await widget.audio.stop();
      recording = false;
      if (path == null) {
        throw StateError('Aucun fichier audio produit.');
      }
      await widget.controller.storeTake(
        speaker: speaker,
        prompt: prompt,
        temporaryPath: path,
        autoStopped: autoStopped,
      );
      HapticFeedback.mediumImpact();
      if (mounted && autoStopped) {
        _message(context, 'Arrêt automatique à 15 secondes : prise douteuse.');
      }
    } on Object catch (error) {
      await widget.audio.cancel();
      if (mounted) {
        _message(context, 'Prise refusée : $error', error: true);
      }
    } finally {
      if (mounted) {
        setState(() {
          recording = false;
          finishing = false;
        });
      }
    }
  }

  Future<void> _listen() async {
    final current = take;
    if (current == null) {
      return;
    }
    try {
      await widget.platform.play(
        widget.controller.takeFile(speaker, current).path,
      );
    } on Object catch (error) {
      if (mounted) {
        _message(context, 'Lecture impossible : $error', error: true);
      }
    }
  }

  Future<void> _listenExample() async {
    final path = examplePath;
    if (path == null) {
      _message(
        context,
        'Aucun exemple audio pour cette consigne.',
        error: true,
      );
      return;
    }
    try {
      await widget.platform.play(path);
    } on Object catch (error) {
      if (mounted) {
        _message(
          context,
          'Lecture de l’exemple impossible : $error',
          error: true,
        );
      }
    }
  }

  Future<void> _next() async {
    if (take == null || recording || finishing) {
      return;
    }
    if (index + 1 >= speaker.prompts.length) {
      await Navigator.pushReplacement(
        context,
        MaterialPageRoute<void>(
          builder: (_) => ReviewScreen(
            controller: widget.controller,
            audio: widget.audio,
            platform: widget.platform,
            speaker: speaker,
          ),
        ),
      );
      return;
    }
    setState(() => index++);
    speaker.currentIndex = index;
    await widget.controller.save();
  }

  @override
  Widget build(BuildContext context) {
    final assessment = widget.controller.assess(speaker, prompt);
    return PopScope(
      canPop: !recording && !finishing,
      child: Scaffold(
        appBar: AppBar(
          title: Text(speaker.name),
          actions: <Widget>[
            Center(
              child: Padding(
                padding: const EdgeInsets.only(right: 18),
                child: Text(
                  '${index + 1} / ${speaker.prompts.length}',
                  style: const TextStyle(fontWeight: FontWeight.w700),
                ),
              ),
            ),
          ],
        ),
        body: SafeArea(
          child: Column(
            children: <Widget>[
              LinearProgressIndicator(
                value: (index + 1) / speaker.prompts.length,
              ),
              Expanded(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.fromLTRB(22, 28, 22, 18),
                  child: Column(
                    children: <Widget>[
                      const Text(
                        'Dites naturellement ce que signifie :',
                        style: TextStyle(color: Colors.black54),
                      ),
                      const SizedBox(height: 34),
                      Semantics(
                        header: true,
                        child: Text(
                          prompt.display,
                          textAlign: TextAlign.center,
                          style: const TextStyle(
                            fontSize: 52,
                            height: 1.05,
                            fontWeight: FontWeight.w900,
                            letterSpacing: -1.5,
                          ),
                        ),
                      ),
                      const SizedBox(height: 22),
                      Text(
                        prompt.zarmaText,
                        textAlign: TextAlign.center,
                        style: const TextStyle(
                          color: Colors.black45,
                          fontSize: 17,
                        ),
                      ),
                      Text(
                        prompt.id,
                        style: const TextStyle(
                          color: Colors.black38,
                          fontSize: 12,
                        ),
                      ),
                      const SizedBox(height: 24),
                      SizedBox(
                        width: double.infinity,
                        child: FilledButton.tonalIcon(
                          onPressed: recording || preparing || finishing
                              ? null
                              : _listenExample,
                          icon: const Icon(Icons.volume_up, size: 32),
                          label: const Padding(
                            padding: EdgeInsets.symmetric(vertical: 4),
                            child: Text(
                              'ÉCOUTER L’EXEMPLE',
                              style: TextStyle(
                                fontSize: 18,
                                fontWeight: FontWeight.w900,
                              ),
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(height: 12),
                      const Row(
                        children: <Widget>[
                          Expanded(child: Divider()),
                          Padding(
                            padding: EdgeInsets.symmetric(horizontal: 12),
                            child: Text(
                              'PUIS RÉPÉTEZ',
                              style: TextStyle(
                                color: Colors.black54,
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                          ),
                          Expanded(child: Divider()),
                        ],
                      ),
                      const SizedBox(height: 18),
                      Listener(
                        onPointerDown: (_) => _press(),
                        onPointerUp: (_) => _release(),
                        onPointerCancel: (_) => _release(),
                        child: AnimatedContainer(
                          duration: const Duration(milliseconds: 120),
                          width: recording ? 150 : 140,
                          height: recording ? 150 : 140,
                          decoration: BoxDecoration(
                            color: recording
                                ? const Color(0xffb3261e)
                                : Theme.of(context).colorScheme.primary,
                            shape: BoxShape.circle,
                            boxShadow: <BoxShadow>[
                              BoxShadow(
                                color: Colors.black.withValues(alpha: 0.18),
                                blurRadius: recording ? 4 : 14,
                                offset: const Offset(0, 5),
                              ),
                            ],
                          ),
                          child: Column(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: <Widget>[
                              Icon(
                                recording ? Icons.graphic_eq : Icons.mic,
                                size: 42,
                                color: Colors.white,
                              ),
                              const SizedBox(height: 6),
                              Text(
                                finishing
                                    ? 'PATIENTEZ'
                                    : recording
                                    ? 'PARLEZ'
                                    : preparing
                                    ? 'PRÉPARATION'
                                    : 'MAINTENEZ',
                                style: const TextStyle(
                                  color: Colors.white,
                                  fontWeight: FontWeight.w900,
                                  fontSize: 13,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                      const SizedBox(height: 12),
                      Text(
                        recording
                            ? 'Relâchez quand vous avez fini'
                            : 'Maintenez le bouton pendant toute la phrase',
                        style: const TextStyle(color: Colors.black54),
                        textAlign: TextAlign.center,
                      ),
                      if (take != null) ...<Widget>[
                        const SizedBox(height: 20),
                        _QualityCard(assessment: assessment, take: take!),
                      ],
                    ],
                  ),
                ),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(14, 6, 14, 14),
                child: Row(
                  children: <Widget>[
                    Expanded(
                      child: TextButton.icon(
                        onPressed: take == null || recording ? null : _listen,
                        icon: const Icon(Icons.play_arrow),
                        label: const Text('Ma prise'),
                      ),
                    ),
                    Expanded(
                      child: TextButton.icon(
                        onPressed: take == null || recording
                            ? null
                            : () => _message(
                                context,
                                'Maintenez le bouton pour remplacer cette prise.',
                              ),
                        icon: const Icon(Icons.refresh),
                        label: const Text('Refaire'),
                      ),
                    ),
                    Expanded(
                      child: FilledButton(
                        onPressed: take == null || recording || finishing
                            ? null
                            : _next,
                        child: Text(
                          index + 1 == speaker.prompts.length
                              ? 'Revue'
                              : 'Suivant',
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _QualityCard extends StatelessWidget {
  const _QualityCard({required this.assessment, required this.take});

  final QualityAssessment assessment;
  final Take take;

  @override
  Widget build(BuildContext context) {
    final label = switch (assessment.level) {
      QualityLevel.good => 'Bonne prise',
      QualityLevel.warning => 'Prise douteuse',
      QualityLevel.bad => 'Prise inutilisable',
      QualityLevel.missing => 'Prise manquante',
    };
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: qualityColor(assessment.level).withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: qualityColor(assessment.level)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              QualityDot(level: assessment.level),
              const SizedBox(width: 9),
              Text(label, style: const TextStyle(fontWeight: FontWeight.w800)),
              const Spacer(),
              Text('${take.durationSeconds.toStringAsFixed(2)} s'),
            ],
          ),
          if (assessment.reasons.isNotEmpty) ...<Widget>[
            const SizedBox(height: 6),
            Text(assessment.reasons.join(' · ')),
          ],
        ],
      ),
    );
  }
}

class ReviewScreen extends StatefulWidget {
  const ReviewScreen({
    super.key,
    required this.controller,
    required this.audio,
    required this.platform,
    required this.speaker,
  });

  final AppController controller;
  final AudioCaptureService audio;
  final PlatformBridge platform;
  final Speaker speaker;

  @override
  State<ReviewScreen> createState() => _ReviewScreenState();
}

class _ReviewScreenState extends State<ReviewScreen> {
  bool doubtfulOnly = false;
  bool exporting = false;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: widget.controller,
      builder: (context, _) {
        final speaker = widget.speaker;
        final prompts = speaker.prompts.where((prompt) {
          if (!doubtfulOnly) {
            return true;
          }
          return widget.controller.assess(speaker, prompt).level !=
              QualityLevel.good;
        }).toList();
        final doubtful = speaker.prompts
            .where(
              (prompt) =>
                  widget.controller.assess(speaker, prompt).level !=
                  QualityLevel.good,
            )
            .length;
        return Scaffold(
          appBar: AppBar(title: const Text('Revue et export')),
          body: SafeArea(
            child: Column(
              children: <Widget>[
                Padding(
                  padding: const EdgeInsets.fromLTRB(18, 8, 18, 10),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: <Widget>[
                      Text(
                        '${speaker.name} · ${speaker.folderName}',
                        style: Theme.of(context).textTheme.titleLarge?.copyWith(
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        '${speaker.takes.length}/${speaker.prompts.length} prises · '
                        '$doubtful à revoir',
                      ),
                      const SizedBox(height: 8),
                      LinearProgressIndicator(
                        value: speaker.takes.length / speaker.prompts.length,
                      ),
                      SwitchListTile(
                        contentPadding: EdgeInsets.zero,
                        title: const Text(
                          'Ne montrer que les prises douteuses',
                        ),
                        value: doubtfulOnly,
                        onChanged: (value) =>
                            setState(() => doubtfulOnly = value),
                      ),
                    ],
                  ),
                ),
                const Divider(height: 1),
                Expanded(
                  child: prompts.isEmpty
                      ? const Center(child: Text('Aucune prise douteuse.'))
                      : ListView.separated(
                          itemCount: prompts.length,
                          separatorBuilder: (_, _) => const Divider(height: 1),
                          itemBuilder: (context, listIndex) {
                            final prompt = prompts[listIndex];
                            final take = speaker.takes[prompt.id];
                            final assessment = widget.controller.assess(
                              speaker,
                              prompt,
                            );
                            final originalIndex = speaker.prompts.indexOf(
                              prompt,
                            );
                            return ListTile(
                              leading: QualityDot(level: assessment.level),
                              title: Text(
                                prompt.display,
                                style: const TextStyle(
                                  fontWeight: FontWeight.w700,
                                ),
                              ),
                              subtitle: Text(
                                assessment.reasons.isEmpty
                                    ? '${prompt.zarmaText} · '
                                          '${take?.durationSeconds.toStringAsFixed(2)} s'
                                    : assessment.reasons.join(' · '),
                                maxLines: 2,
                                overflow: TextOverflow.ellipsis,
                              ),
                              trailing: Row(
                                mainAxisSize: MainAxisSize.min,
                                children: <Widget>[
                                  IconButton(
                                    tooltip: 'Écouter',
                                    onPressed: take == null
                                        ? null
                                        : () => widget.platform.play(
                                            widget.controller
                                                .takeFile(speaker, take)
                                                .path,
                                          ),
                                    icon: const Icon(Icons.play_arrow),
                                  ),
                                  IconButton(
                                    tooltip: take == null
                                        ? 'Enregistrer'
                                        : 'Refaire',
                                    onPressed: () => _record(originalIndex),
                                    icon: Icon(
                                      take == null ? Icons.mic : Icons.refresh,
                                    ),
                                  ),
                                ],
                              ),
                            );
                          },
                        ),
                ),
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 10, 16, 14),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: <Widget>[
                      FilledButton.icon(
                        onPressed: exporting || speaker.takes.isEmpty
                            ? null
                            : () => _export(oneSpeaker: true),
                        icon: const Icon(Icons.share),
                        label: Text(
                          exporting
                              ? 'Préparation du ZIP…'
                              : 'Exporter ce locuteur',
                        ),
                      ),
                      const SizedBox(height: 6),
                      OutlinedButton.icon(
                        onPressed:
                            exporting ||
                                !widget.controller.speakers.any(
                                  (item) => item.takes.isNotEmpty,
                                )
                            ? null
                            : () => _export(oneSpeaker: false),
                        icon: const Icon(Icons.archive_outlined),
                        label: const Text('Exporter tous les locuteurs'),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Future<void> _record(int promptIndex) async {
    await Navigator.push(
      context,
      MaterialPageRoute<void>(
        builder: (_) => RecordingScreen(
          controller: widget.controller,
          audio: widget.audio,
          platform: widget.platform,
          speaker: widget.speaker,
          initialIndex: promptIndex,
        ),
      ),
    );
  }

  Future<void> _export({required bool oneSpeaker}) async {
    final speaker = widget.speaker;
    final missing = speaker.prompts.length - speaker.takes.length;
    if (oneSpeaker && missing > 0) {
      final continueExport = await showDialog<bool>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          title: const Text('Séance incomplète'),
          content: Text(
            '$missing consigne(s) n’ont pas encore de prise. '
            'Le ZIP ne contiendra que les fichiers enregistrés.',
          ),
          actions: <Widget>[
            TextButton(
              onPressed: () => Navigator.pop(dialogContext, false),
              child: const Text('Revenir à la revue'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(dialogContext, true),
              child: const Text('Exporter quand même'),
            ),
          ],
        ),
      );
      if (continueExport != true) {
        return;
      }
    }
    setState(() => exporting = true);
    try {
      final File zip = oneSpeaker
          ? await widget.controller.exportSpeaker(speaker)
          : await widget.controller.exportAll();
      await SharePlus.instance.share(
        ShareParams(
          files: <XFile>[XFile(zip.path, mimeType: 'application/zip')],
          subject: 'Corpus vocal zarma',
          text: oneSpeaker
              ? 'Enregistrements de ${speaker.name} (${speaker.code})'
              : 'Corpus vocal zarma — tous les locuteurs',
        ),
      );
    } on Object catch (error) {
      if (mounted) {
        _message(context, 'Export impossible : $error', error: true);
      }
    } finally {
      if (mounted) {
        setState(() => exporting = false);
      }
    }
  }
}

class QualityDot extends StatelessWidget {
  const QualityDot({super.key, required this.level});

  final QualityLevel level;

  @override
  Widget build(BuildContext context) => Semantics(
    label: switch (level) {
      QualityLevel.good => 'qualité bonne',
      QualityLevel.warning => 'qualité douteuse',
      QualityLevel.bad => 'qualité mauvaise',
      QualityLevel.missing => 'prise manquante',
    },
    child: Container(
      width: 15,
      height: 15,
      decoration: BoxDecoration(
        color: qualityColor(level),
        shape: BoxShape.circle,
        border: Border.all(color: Colors.black26),
      ),
    ),
  );
}

Color qualityColor(QualityLevel level) => switch (level) {
  QualityLevel.good => const Color(0xff2e7d32),
  QualityLevel.warning => const Color(0xffed8b00),
  QualityLevel.bad => const Color(0xffc62828),
  QualityLevel.missing => const Color(0xff757575),
};

void _message(BuildContext context, String message, {bool error = false}) {
  ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: error ? Theme.of(context).colorScheme.error : null,
      ),
    );
}
