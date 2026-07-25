import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:zarma_mobile/speech/wav.dart';

/// Assemblage audio : c'est lui qui transforme des mots enregistrés en une
/// phrase. Une erreur ici produit un son inintelligible — ou pire, un nombre
/// tronqué que l'utilisateur cible ne peut pas détecter.
Uint8List wavOf(Uint8List pcm) => wavFromPcm(pcm);

Uint8List tonePcm(int frames) {
  final Uint8List pcm = Uint8List(frames * 2);
  final ByteData view = ByteData.sublistView(pcm);
  for (int i = 0; i < frames; i++) {
    view.setInt16(i * 2, (i % 200) * 100 - 10000, Endian.little);
  }
  return pcm;
}

void main() {
  group('lecture d’un WAV', () {
    test('extrait le PCM d’un WAV canonique', () {
      final Uint8List pcm = tonePcm(1000);
      expect(pcmFromWav(wavOf(pcm)), equals(pcm));
    });

    test('un aller-retour ne perd rien', () {
      final Uint8List pcm = tonePcm(4321);
      expect(pcmFromWav(wavFromPcm(pcmFromWav(wavOf(pcm)))), equals(pcm));
    });

    test('refuse un fichier qui n’est pas un WAV', () {
      final Uint8List bogus = Uint8List.fromList(List<int>.filled(100, 7));
      expect(() => pcmFromWav(bogus), throwsA(isA<WavFormatException>()));
    });

    test('refuse un fichier trop court', () {
      expect(
        () => pcmFromWav(Uint8List(10)),
        throwsA(isA<WavFormatException>()),
      );
    });

    test('refuse un format non canonique plutôt que de rééchantillonner', () {
      // 44,1 kHz stéréo : exactement ce qui sort d'un micro grand public, et
      // exactement ce qu'il ne faut PAS accepter en silence.
      final Uint8List wav = wavOf(tonePcm(100));
      final ByteData view = ByteData.sublistView(wav);
      view.setUint32(24, 44100, Endian.little); // sampleRate
      view.setUint16(22, 2, Endian.little); // channels

      expect(() => pcmFromWav(wav), throwsA(isA<WavFormatException>()));
    });

    test('supporte un chunk optionnel avant les données', () {
      // Beaucoup d'enregistreurs insèrent un chunk LIST : supposer que les
      // données commencent à l'octet 44 produirait un grésillement.
      final Uint8List pcm = tonePcm(50);
      final Uint8List base = wavOf(pcm);
      final Uint8List extra = Uint8List.fromList(<int>[
        ...base.sublist(0, 36),
        ...'LIST'.codeUnits, 4, 0, 0, 0, 1, 2, 3, 4,
        ...base.sublist(36),
      ]);
      final ByteData view = ByteData.sublistView(extra);
      view.setUint32(4, extra.length - 8, Endian.little);

      expect(pcmFromWav(extra), equals(pcm));
    });
  });

  group('assemblage', () {
    test('colle les segments dans l’ordre', () {
      final Uint8List a = tonePcm(100);
      final Uint8List b = tonePcm(50);
      final Uint8List joined = joinPcm(<Uint8List>[a, b], gapSeconds: 0);

      expect(joined.length, a.length + b.length);
      expect(joined.sublist(0, a.length), equals(a));
      expect(joined.sublist(a.length), equals(b));
    });

    test('insère un silence entre deux mots, jamais aux extrémités', () {
      final Uint8List a = tonePcm(100);
      final Uint8List gap = silencePcm(kWordGapSeconds);
      final Uint8List joined = joinPcm(<Uint8List>[a, a, a]);

      expect(joined.length, a.length * 3 + gap.length * 2);
      expect(joined.sublist(0, a.length), equals(a));
      expect(joined.sublist(joined.length - a.length), equals(a));
    });

    test('un seul segment n’ajoute aucun silence', () {
      final Uint8List a = tonePcm(100);
      expect(joinPcm(<Uint8List>[a]).length, a.length);
    });

    test('aucun segment donne un flux vide', () {
      expect(joinPcm(<Uint8List>[]).length, 0);
    });

    test('la durée croît avec le nombre de mots', () {
      final Uint8List a = tonePcm(1600); // 0,1 s
      final double one = pcmDurationSeconds(joinPcm(<Uint8List>[a]));
      final double three = pcmDurationSeconds(joinPcm(<Uint8List>[a, a, a]));

      expect(one, closeTo(0.1, 0.001));
      expect(three, greaterThan(one * 3));
    });
  });

  group('écriture d’un WAV', () {
    test('produit un en-tête canonique lisible', () {
      final Uint8List wav = wavFromPcm(tonePcm(800));
      final ByteData view = ByteData.sublistView(wav);

      expect(String.fromCharCodes(wav.sublist(0, 4)), 'RIFF');
      expect(String.fromCharCodes(wav.sublist(8, 12)), 'WAVE');
      expect(view.getUint16(22, Endian.little), kChannels);
      expect(view.getUint32(24, Endian.little), kSampleRate);
      expect(view.getUint16(34, Endian.little), kBitsPerSample);
      expect(view.getUint32(4, Endian.little), wav.length - 8);
    });
  });
}
