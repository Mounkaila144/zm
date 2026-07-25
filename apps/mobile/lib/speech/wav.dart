/// Assemblage de WAV PCM16 mono 16 kHz — logique pure, sans plugin (story 6.1).
///
/// L'application prononce un nombre en **collant bout à bout** des mots
/// enregistrés. C'est ce qui rend la parole possible sans synthèse vocale
/// entraînée, sans réseau, et sans dépendre d'un service tiers pour une langue
/// que personne ne sert.
///
/// Pendant du `synthesize()` de `scripts/speech/voice_bank.py`, mêmes constantes
/// et même silence inter-mots : ce qu'on entend au casque pendant la préparation
/// de la banque est ce qu'on entend dans l'application.
library;

import 'dart:typed_data';

/// Format canonique du projet, identique à la capture micro (FR1).
const int kSampleRate = 16000;
const int kChannels = 1;
const int kBitsPerSample = 16;

/// Silence inséré entre deux segments — respiration naturelle.
///
/// Même valeur que `WORD_GAP_SECONDS` côté outillage Python. Trop court, les
/// mots se chevauchent ; trop long, l'énoncé sonne comme une liste.
const double kWordGapSeconds = 0.06;

/// Un WAV illisible ou hors format : erreur contrôlée, jamais un silence discret.
class WavFormatException implements Exception {
  const WavFormatException(this.message);

  final String message;

  @override
  String toString() => 'WavFormatException: $message';
}

/// Échantillons PCM d'un WAV canonique, en-tête retiré.
///
/// Le format est **vérifié**, jamais converti à la volée : un rééchantillonnage
/// silencieux dégraderait l'intelligibilité sans que personne le sache. Les
/// fichiers sont normalisés en amont par `scripts/speech/prepare_bank.py`.
Uint8List pcmFromWav(Uint8List bytes) {
  if (bytes.length < 44) {
    throw const WavFormatException('fichier trop court pour être un WAV');
  }
  final ByteData data = ByteData.sublistView(bytes);

  if (_ascii(bytes, 0, 4) != 'RIFF' || _ascii(bytes, 8, 4) != 'WAVE') {
    throw const WavFormatException('en-tête RIFF/WAVE absent');
  }

  // Les WAV réels contiennent des chunks optionnels (LIST, fact…) : on les
  // parcourt plutôt que de supposer que `data` commence à l'octet 44.
  int offset = 12;
  int? channels;
  int? sampleRate;
  int? bits;
  while (offset + 8 <= bytes.length) {
    final String id = _ascii(bytes, offset, 4);
    final int size = data.getUint32(offset + 4, Endian.little);
    final int body = offset + 8;

    if (id == 'fmt ') {
      if (body + 16 > bytes.length) {
        throw const WavFormatException('chunk fmt tronqué');
      }
      channels = data.getUint16(body + 2, Endian.little);
      sampleRate = data.getUint32(body + 4, Endian.little);
      bits = data.getUint16(body + 14, Endian.little);
    } else if (id == 'data') {
      if (channels != kChannels || sampleRate != kSampleRate || bits != kBitsPerSample) {
        throw WavFormatException(
          'format non canonique : ${channels}ch ${sampleRate}Hz ${bits}bits '
          '(attendu ${kChannels}ch ${kSampleRate}Hz ${kBitsPerSample}bits)',
        );
      }
      final int end = (body + size <= bytes.length) ? body + size : bytes.length;
      return Uint8List.sublistView(bytes, body, end);
    }
    // Les chunks sont alignés sur 2 octets.
    offset = body + size + (size.isOdd ? 1 : 0);
  }
  throw const WavFormatException('chunk data introuvable');
}

/// PCM d'un silence de [seconds].
Uint8List silencePcm(double seconds) {
  final int frames = (seconds * kSampleRate).round();
  return Uint8List(frames * (kBitsPerSample ~/ 8) * kChannels);
}

/// Colle les segments PCM bout à bout, séparés d'un court silence.
Uint8List joinPcm(List<Uint8List> segments, {double gapSeconds = kWordGapSeconds}) {
  if (segments.isEmpty) {
    return Uint8List(0);
  }
  final Uint8List gap = silencePcm(gapSeconds);
  final int total =
      segments.fold<int>(0, (sum, s) => sum + s.length) + gap.length * (segments.length - 1);

  final Uint8List out = Uint8List(total);
  int cursor = 0;
  for (int i = 0; i < segments.length; i++) {
    if (i > 0) {
      out.setRange(cursor, cursor + gap.length, gap);
      cursor += gap.length;
    }
    out.setRange(cursor, cursor + segments[i].length, segments[i]);
    cursor += segments[i].length;
  }
  return out;
}

/// Enveloppe du PCM dans un WAV canonique jouable.
Uint8List wavFromPcm(Uint8List pcm) {
  const int headerSize = 44;
  const int byteRate = kSampleRate * kChannels * (kBitsPerSample ~/ 8);
  const int blockAlign = kChannels * (kBitsPerSample ~/ 8);

  final Uint8List out = Uint8List(headerSize + pcm.length);
  final ByteData data = ByteData.sublistView(out);

  _writeAscii(out, 0, 'RIFF');
  data.setUint32(4, 36 + pcm.length, Endian.little);
  _writeAscii(out, 8, 'WAVE');
  _writeAscii(out, 12, 'fmt ');
  data.setUint32(16, 16, Endian.little); // taille du chunk fmt (PCM)
  data.setUint16(20, 1, Endian.little); // format 1 = PCM entier
  data.setUint16(22, kChannels, Endian.little);
  data.setUint32(24, kSampleRate, Endian.little);
  data.setUint32(28, byteRate, Endian.little);
  data.setUint16(32, blockAlign, Endian.little);
  data.setUint16(34, kBitsPerSample, Endian.little);
  _writeAscii(out, 36, 'data');
  data.setUint32(40, pcm.length, Endian.little);
  out.setRange(headerSize, headerSize + pcm.length, pcm);
  return out;
}

/// Durée d'un flux PCM canonique, en secondes.
double pcmDurationSeconds(Uint8List pcm) =>
    pcm.length / (kSampleRate * kChannels * (kBitsPerSample ~/ 8));

String _ascii(Uint8List bytes, int start, int length) =>
    String.fromCharCodes(bytes.sublist(start, start + length));

void _writeAscii(Uint8List target, int offset, String value) {
  for (int i = 0; i < value.length; i++) {
    target[offset + i] = value.codeUnitAt(i);
  }
}
