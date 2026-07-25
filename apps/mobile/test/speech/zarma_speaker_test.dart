import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:zarma_mobile/speech/voice_bank.dart';
import 'package:zarma_mobile/speech/wav.dart';
import 'package:zarma_mobile/speech/zarma_speaker.dart';

/// La propriété de sûreté de la restitution vocale : **rien plutôt qu'un
/// énoncé tronqué**. Un utilisateur qui ne lit pas ne peut pas détecter qu'on
/// lui a dit « vingt » au lieu de « vingt-trois » (FR21).
class FakeBundle extends CachingAssetBundle {
  FakeBundle(this.assets);

  final Map<String, Uint8List> assets;

  @override
  Future<ByteData> load(String key) async {
    final Uint8List? bytes = assets[key];
    if (bytes == null) {
      throw FlutterError('asset absent : $key');
    }
    return ByteData.sublistView(bytes);
  }
}

Uint8List wordWav(int frames) => wavFromPcm(Uint8List(frames * 2));

void main() {
  late List<Uint8List> played;
  late FakeBundle bundle;

  VoiceBank bankOf(Iterable<String> words,
      {Iterable<String> prompts = const <String>[]}) {
    return VoiceBank(
      assetByWord: <String, String>{
        for (final String w in words) w: 'assets/voice/words/$w.wav',
      },
      assetByPrompt: <String, String>{
        for (final String p in prompts) p: 'assets/voice/prompts/$p.wav',
      },
    );
  }

  ZarmaSpeaker speakerOf(VoiceBank bank) {
    return ZarmaSpeaker(
      bank: bank,
      bundle: bundle,
      play: (Uint8List wav) async => played.add(wav),
    );
  }

  setUp(() {
    played = <Uint8List>[];
    bundle = FakeBundle(<String, Uint8List>{
      'assets/voice/words/waranza.wav': wordWav(1600),
      'assets/voice/words/cindi.wav': wordWav(800),
      'assets/voice/words/hakou.wav': wordWav(1200),
      'assets/voice/prompts/confirm.wav': wordWav(3200),
      'assets/voice/prompts/cannot_answer.wav': wordWav(2400),
    });
  });

  group('découpage de la forme zarma', () {
    test('un mot par segment, dans l’ordre du serveur', () {
      expect(
        utteranceFromZarma('waranza cindi hakou'),
        const <VoiceSegment>[
          VoiceSegment.word('waranza'),
          VoiceSegment.word('cindi'),
          VoiceSegment.word('hakou'),
        ],
      );
    });

    test('ignore les espaces superflus', () {
      expect(utteranceFromZarma('  waranza   cindi '), hasLength(2));
    });

    test('la confirmation place la consigne en tête', () {
      final List<VoiceSegment> utterance =
          confirmationUtterance(utteranceFromZarma('waranza'));
      expect(utterance.first, const VoiceSegment.prompt(kPromptConfirm));
      expect(utterance.last, const VoiceSegment.word('waranza'));
    });

    test('un refus se prononce par sa consigne', () {
      expect(refusalUtterance(), const <VoiceSegment>[
        VoiceSegment.prompt(kPromptCannotAnswer),
      ]);
    });
  });

  group('fail-closed', () {
    test('un mot manquant fait taire tout l’énoncé', () async {
      final ZarmaSpeaker speaker =
          speakerOf(bankOf(<String>['waranza', 'cindi']));

      final SpeechOutcome outcome =
          await speaker.speak(utteranceFromZarma('waranza cindi hakou'));

      expect(outcome, SpeechOutcome.incomplete);
      expect(played, isEmpty, reason: 'rien ne doit être joué à moitié');
    });

    test('la consigne manquante bloque toute la confirmation', () async {
      final ZarmaSpeaker speaker = speakerOf(bankOf(<String>['waranza']));

      final SpeechOutcome outcome = await speaker.speak(
        confirmationUtterance(utteranceFromZarma('waranza')),
      );

      expect(outcome, SpeechOutcome.incomplete);
      expect(played, isEmpty);
    });

    test('un énoncé vide ne joue rien', () async {
      final ZarmaSpeaker speaker = speakerOf(bankOf(<String>['waranza']));
      expect(await speaker.speak(<VoiceSegment>[]), SpeechOutcome.incomplete);
      expect(played, isEmpty);
    });

    test('les segments manquants sont nommés, pas seulement comptés', () {
      final ZarmaSpeaker speaker = speakerOf(bankOf(<String>['waranza']));
      expect(
        speaker.missing(utteranceFromZarma('waranza cindi cindi hakou')),
        const <VoiceSegment>[
          VoiceSegment.word('cindi'),
          VoiceSegment.word('hakou')
        ],
      );
    });
  });

  group('prononciation', () {
    test('assemble les mots présents et joue une seule fois', () async {
      final ZarmaSpeaker speaker =
          speakerOf(bankOf(<String>['waranza', 'cindi', 'hakou']));

      final SpeechOutcome outcome =
          await speaker.speak(utteranceFromZarma('waranza cindi hakou'));

      expect(outcome, SpeechOutcome.spoken);
      expect(played, hasLength(1));
    });

    test('le flux joué contient bien les trois mots et leurs silences',
        () async {
      final ZarmaSpeaker speaker =
          speakerOf(bankOf(<String>['waranza', 'cindi', 'hakou']));
      await speaker.speak(utteranceFromZarma('waranza cindi hakou'));

      final Uint8List pcm = pcmFromWav(played.single);
      const int words = (1600 + 800 + 1200) * 2;
      final int gaps = silencePcm(kWordGapSeconds).length * 2;
      expect(pcm.length, words + gaps);
    });

    test('un énoncé plus long dure plus longtemps', () async {
      final ZarmaSpeaker speaker =
          speakerOf(bankOf(<String>['waranza', 'cindi', 'hakou']));

      await speaker.speak(utteranceFromZarma('waranza'));
      await speaker.speak(utteranceFromZarma('waranza cindi hakou'));

      expect(
        pcmDurationSeconds(pcmFromWav(played[1])),
        greaterThan(pcmDurationSeconds(pcmFromWav(played.first))),
      );
    });

    test('le refus est audible', () async {
      final ZarmaSpeaker speaker = speakerOf(
        bankOf(<String>[], prompts: <String>[kPromptCannotAnswer]),
      );

      expect(await speaker.speak(refusalUtterance()), SpeechOutcome.spoken);
      expect(played, hasLength(1));
    });

    test('une panne de lecture ne fait pas tomber l’écran', () async {
      final ZarmaSpeaker speaker = ZarmaSpeaker(
        bank: bankOf(<String>['waranza']),
        bundle: bundle,
        play: (Uint8List wav) async => throw Exception('haut-parleur occupé'),
      );

      expect(
        await speaker.speak(utteranceFromZarma('waranza')),
        SpeechOutcome.failed,
      );
    });
  });

  group('banque', () {
    test('une banque vide ne dit rien mais ne dit jamais faux', () async {
      final ZarmaSpeaker speaker = speakerOf(const VoiceBank.empty());
      expect(
        await speaker.speak(utteranceFromZarma('waranza')),
        SpeechOutcome.incomplete,
      );
      expect(played, isEmpty);
    });

    test('canSay reflète exactement ce qui est jouable', () {
      final VoiceBank bank = bankOf(<String>['waranza', 'cindi']);
      expect(bank.canSay(utteranceFromZarma('waranza cindi')), isTrue);
      expect(bank.canSay(utteranceFromZarma('waranza hakou')), isFalse);
      expect(bank.canSay(<VoiceSegment>[]), isFalse);
    });
  });
}
