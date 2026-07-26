/// Banque vocale embarquée : quels mots l'application sait prononcer (story 6.1).
///
/// L'utilisateur cible **ne lit pas**. Afficher « 38 » ne suffit donc pas : le
/// résultat doit être *dit*. Le vocabulaire des nombres étant fermé (40 mots),
/// il suffit d'assembler des mots enregistrés — pas de synthèse vocale
/// entraînée, et surtout **aucun réseau** : sur un marché, la connexion n'est
/// pas acquise.
///
/// Deux règles, les mêmes que côté outillage Python :
///
/// - **Source unique.** La suite de mots à prononcer vient de la forme canonique
///   renvoyée par l'API (`zarma_text`, `result_zarma_text`), elle-même produite
///   par `zarma_numbers`. Le mobile ne recompose jamais un nombre.
/// - **Fail-closed (FR21).** S'il manque un seul segment, **rien** n'est joué.
///   Un résultat prononcé à moitié serait indétectable pour la cible — donc pire
///   que le silence.
library;

import 'package:flutter/services.dart';

/// Nature d'un segment : un mot composable, ou une consigne enregistrée entière.
enum VoiceSegmentKind { word, prompt }

/// Consignes attendues dans les assets.
const String kPromptConfirm = 'confirm';
const String kPromptCannotAnswer = 'cannot_answer';

/// Consigne jouée quand aucun nombre n'a pu être identifié (repérage échoué,
/// pas un calcul refusé — voir [kPromptCannotAnswer] pour ce second cas).
const String kPromptRepeat = 'repeat';

/// Un morceau d'énoncé à prononcer.
class VoiceSegment {
  const VoiceSegment.word(this.key) : kind = VoiceSegmentKind.word;
  const VoiceSegment.prompt(this.key) : kind = VoiceSegmentKind.prompt;

  final VoiceSegmentKind kind;
  final String key;

  @override
  bool operator ==(Object other) =>
      other is VoiceSegment && other.kind == kind && other.key == key;

  @override
  int get hashCode => Object.hash(kind, key);

  @override
  String toString() => '${kind.name}:$key';
}

/// Segments prononçant une forme zarma canonique (« waranza cindi hakou »).
///
/// Se contente de découper : les formes ne sont jamais réécrites ici.
List<VoiceSegment> utteranceFromZarma(String zarmaText) {
  return zarmaText
      .split(' ')
      .where((String word) => word.isNotEmpty)
      .map(VoiceSegment.word)
      .toList(growable: false);
}

/// Consigne de confirmation suivie de l'énoncé à confirmer.
///
/// C'est le point que la story identifie comme bloquant : la confirmation
/// affichée (« C'est bien 42 ? ») est inopérante pour la cible, alors qu'elle
/// est le chemin nominal. La même modalité vocale la rend utilisable.
List<VoiceSegment> confirmationUtterance(List<VoiceSegment> inner) {
  return <VoiceSegment>[const VoiceSegment.prompt(kPromptConfirm), ...inner];
}

/// Consigne annonçant qu'aucune réponse n'existe (résultat hors domaine).
///
/// Un refus **doit** être audible : rester silencieux serait indistinguable
/// d'une panne pour l'utilisateur (AC4/FR21).
List<VoiceSegment> refusalUtterance() {
  return const <VoiceSegment>[VoiceSegment.prompt(kPromptCannotAnswer)];
}

/// Consigne annonçant qu'aucun nombre n'a pu être identifié dans la voix.
///
/// Même principe que [refusalUtterance] : silence et échec sont
/// indistinguables pour qui ne lit pas, donc jamais de silence ici non plus.
List<VoiceSegment> repeatUtterance() {
  return const <VoiceSegment>[VoiceSegment.prompt(kPromptRepeat)];
}

/// Fichiers audio réellement embarqués dans l'application.
class VoiceBank {
  const VoiceBank({required this.assetByWord, required this.assetByPrompt});

  /// Banque vide — l'application se taira, mais ne dira jamais faux.
  const VoiceBank.empty()
      : assetByWord = const <String, String>{},
        assetByPrompt = const <String, String>{};

  /// Construit la banque depuis le manifeste d'assets.
  ///
  /// Rien n'est codé en dur : **ce qui est livré définit ce qui est prononçable**.
  /// Ajouter un mot enregistré suffit à l'activer, y compris pour une opération
  /// dont la forme zarma vient d'être validée.
  static Future<VoiceBank> load(
    AssetBundle bundle, {
    String wordsPath = 'assets/voice/words/',
    String promptsPath = 'assets/voice/prompts/',
  }) async {
    final AssetManifest manifest =
        await AssetManifest.loadFromAssetBundle(bundle);
    final Map<String, String> words = <String, String>{};
    final Map<String, String> prompts = <String, String>{};

    for (final String asset in manifest.listAssets()) {
      if (!asset.endsWith('.wav')) {
        continue;
      }
      final String name = asset.split('/').last.replaceAll('.wav', '');
      if (asset.startsWith(wordsPath)) {
        words[name] = asset;
      } else if (asset.startsWith(promptsPath)) {
        prompts[name] = asset;
      }
    }
    return VoiceBank(assetByWord: words, assetByPrompt: prompts);
  }

  final Map<String, String> assetByWord;
  final Map<String, String> assetByPrompt;

  String? assetFor(VoiceSegment segment) {
    return segment.kind == VoiceSegmentKind.prompt
        ? assetByPrompt[segment.key]
        : assetByWord[segment.key];
  }

  /// Segments absents, dans l'ordre et sans doublon.
  List<VoiceSegment> missing(List<VoiceSegment> utterance) {
    final List<VoiceSegment> absent = <VoiceSegment>[];
    for (final VoiceSegment segment in utterance) {
      if (assetFor(segment) == null && !absent.contains(segment)) {
        absent.add(segment);
      }
    }
    return absent;
  }

  bool canSay(List<VoiceSegment> utterance) =>
      utterance.isNotEmpty && missing(utterance).isEmpty;
}
