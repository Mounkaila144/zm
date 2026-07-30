/// Prononciation d'un énoncé zarma par concaténation (story 6.1, task 6).
///
/// Assemble les mots de la banque embarquée et les joue. **Hors ligne** par
/// construction : les WAV sont des assets de l'application, rien ne transite par
/// le réseau au moment de parler.
///
/// La logique métier vit ici, pas dans les widgets (règle d'architecture) : un
/// écran demande « dis ceci », il ne sait ni comment les mots sont trouvés, ni
/// comment l'audio est assemblé.
library;

import 'dart:async';
import 'dart:io';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:path_provider/path_provider.dart';
import 'package:zarma_mobile/speech/voice_bank.dart';
import 'package:zarma_mobile/speech/wav.dart';

/// Ce qui s'est passé quand on a demandé à parler — jamais un simple `bool`.
enum SpeechOutcome {
  /// L'énoncé a été assemblé et joué.
  spoken,

  /// Un segment manquait à la banque : **rien** n'a été joué (fail-closed).
  incomplete,

  /// L'audio est bien là mais la lecture a échoué (matériel, plugin).
  failed,
}

/// Joue un flux WAV déjà assemblé. Isolé pour rester testable sans plugin.
typedef WavPlayer = Future<void> Function(Uint8List wav);

class ZarmaSpeaker {
  ZarmaSpeaker({
    required this._bank,
    required this._bundle,
    required this._play,
  });

  final VoiceBank _bank;
  final AssetBundle _bundle;
  final WavPlayer _play;

  /// Segments manquants pour prononcer [utterance] (vide = prononçable).
  List<VoiceSegment> missing(List<VoiceSegment> utterance) =>
      _bank.missing(utterance);

  /// Assemble puis joue [utterance].
  ///
  /// **Fail-closed (FR21)** : si un seul segment manque, rien n'est joué et le
  /// résultat vaut [SpeechOutcome.incomplete]. Prononcer « vingt » pour
  /// « vingt-trois » serait indétectable pour un utilisateur qui ne lit pas.
  Future<SpeechOutcome> speak(List<VoiceSegment> utterance) async {
    if (utterance.isEmpty || _bank.missing(utterance).isNotEmpty) {
      return SpeechOutcome.incomplete;
    }
    try {
      final List<Uint8List> segments = <Uint8List>[];
      for (final VoiceSegment segment in utterance) {
        final ByteData data = await _bundle.load(_bank.assetFor(segment)!);
        segments.add(pcmFromWav(data.buffer.asUint8List()));
      }
      await _play(wavFromPcm(joinPcm(segments)));
      return SpeechOutcome.spoken;
    } on WavFormatException {
      return SpeechOutcome.failed;
    } catch (_) {
      // Une panne de lecture ne doit jamais faire tomber l'écran : l'utilisateur
      // garde l'affichage, et le bouton « Réécouter » lui permet de réessayer.
      return SpeechOutcome.failed;
    }
  }
}

/// Banque chargée une seule fois depuis les assets embarqués.
final voiceBankProvider = FutureProvider<VoiceBank>((ref) {
  return VoiceBank.load(rootBundle);
});

/// Lecteur audio réel — remplacé par un faux dans les tests.
///
/// L'énoncé passe par un **fichier temporaire**, pas par `BytesSource` :
/// `audioplayers` ne l'implémente pas sur iOS/macOS (`setSourceBytes is not
/// currently implemented on iOS`), et l'échec y était muet — l'écran s'affichait
/// sans qu'aucun son ne sorte. `DeviceFileSource` est le seul chemin commun à
/// toutes les plateformes cibles.
final wavPlayerProvider = Provider<WavPlayer>((ref) {
  final AudioPlayer player = AudioPlayer();
  int utteranceCount = 0;
  File? previous;

  Future<void> discard(File? file) async {
    if (file == null) return;
    try {
      await file.delete();
    } catch (_) {
      // Un temporaire qui survit ne casse rien : le système le nettoiera.
    }
  }

  ref.onDispose(() {
    player.dispose();
    unawaited(discard(previous));
  });

  return (Uint8List wav) async {
    await player.stop();

    if (Platform.isIOS) {
      // `record` bascule la session iOS en `playAndRecord` et ne la restaure
      // pas ; `audioplayers` n'applique sa catégorie qu'au démarrage du plugin.
      // Sans ce rappel, tout ce qui suit un enregistrement sortirait par
      // l'écouteur au lieu du haut-parleur — inaudible sur un marché.
      await player.setAudioContext(
        AudioContext(iOS: AudioContextIOS()),
      );
    }

    // Nom unique par énoncé : AVPlayer garde en cache le contenu d'une URL déjà
    // vue, réécrire le même chemin rejouerait l'énoncé précédent.
    final Directory dir = await getTemporaryDirectory();
    final File file = File('${dir.path}/zarma_utterance_${utteranceCount++}.wav');
    await file.writeAsBytes(wav, flush: true);

    final Future<void> completed = player.onPlayerComplete.first;
    try {
      await player.play(DeviceFileSource(file.path));
      await completed;
    } finally {
      // On ne supprime qu'au tour suivant : le lecteur peut encore tenir le
      // descripteur juste après `onPlayerComplete`.
      await discard(previous);
      previous = file;
    }
  };
});

/// Prononciateur prêt à l'emploi, ou `null` tant que la banque charge.
final zarmaSpeakerProvider = Provider<ZarmaSpeaker?>((ref) {
  final AsyncValue<VoiceBank> bank = ref.watch(voiceBankProvider);
  return bank.maybeWhen(
    data: (VoiceBank value) => ZarmaSpeaker(
      bank: value,
      bundle: rootBundle,
      play: ref.watch(wavPlayerProvider),
    ),
    orElse: () => null,
  );
});
