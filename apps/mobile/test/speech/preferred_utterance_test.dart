import 'package:flutter_test/flutter_test.dart';
import 'package:zarma_mobile/speech/voice_bank.dart';

/// Banque factice : ce qu'elle contient définit ce qu'elle sait dire, comme la
/// vraie (`VoiceBank.load` lit le manifeste d'assets).
VoiceBank _bank(List<String> mots) {
  return VoiceBank(
    assetByWord: <String, String>{
      for (final String mot in mots) mot: 'assets/voice/words/$mot.wav',
    },
    assetByPrompt: const <String, String>{},
  );
}

void main() {
  const String canonique = 'ihinka tonton ihinza';
  const String parle = 'ihinka kanga itonton ihinza';

  test('prononce la forme longue quand la banque la connaît', () {
    final VoiceBank banque = _bank(<String>['ihinka', 'ihinza', 'kanga', 'itonton']);

    expect(
      preferredUtterance(canonique, parle, banque),
      utteranceFromZarma(parle),
    );
  });

  test('se replie sur la forme courte tant que les mots longs manquent', () {
    // C'est l'état du jour : `kanga.wav` et `itonton.wav` ne sont pas encore
    // enregistrés. Sans ce repli, la banque étant fail-closed, l'application
    // deviendrait muette sur TOUTES les opérations — sans erreur visible.
    final VoiceBank banque = _bank(<String>['ihinka', 'ihinza', 'tonton']);

    expect(
      preferredUtterance(canonique, parle, banque),
      utteranceFromZarma(canonique),
    );
  });

  test('un repli partiel ne mélange jamais les deux formes', () {
    // `kanga` présent mais `itonton` absent : la forme longue est indisponible
    // en entier, donc on n'en prend aucun morceau. Prononcer « ihinka kanga
    // ihinza » serait pire que la forme courte.
    final VoiceBank banque = _bank(<String>['ihinka', 'ihinza', 'tonton', 'kanga']);

    expect(
      preferredUtterance(canonique, parle, banque),
      utteranceFromZarma(canonique),
    );
  });

  test('sans forme prononcée, garde la canonique', () {
    // Cas d'un nombre seul : le serveur laisse `spoken_text` vide, et d'un
    // client plus ancien qui ne connaît pas le champ.
    final VoiceBank banque = _bank(<String>['zangou']);

    expect(
      preferredUtterance('zangou', '', banque),
      utteranceFromZarma('zangou'),
    );
  });
}
