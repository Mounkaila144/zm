import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:corpus_recorder/zip_writer.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('produit un ZIP standard sans modifier le contenu', () async {
    final directory = await Directory.systemTemp.createTemp('corpus-zip-test-');
    addTearDown(() => directory.delete(recursive: true));
    final destination = File('${directory.path}/corpus.zip');
    final content = Uint8List.fromList(utf8.encode('audio-identique'));

    await writeStoredZip(destination, <ZipEntrySource>[
      ZipEntrySource.fromBytes('zarma_corpus/test/2+3.wav', content),
      ZipEntrySource.fromBytes(
        'zarma_corpus/test/manifest.csv',
        Uint8List.fromList(utf8.encode('fichier,identifiant\n2+3.wav,2+3\n')),
      ),
    ]);

    final bytes = await destination.readAsBytes();
    expect(bytes.sublist(0, 4), <int>[0x50, 0x4b, 0x03, 0x04]);
    final result = await Process.run('unzip', <String>[
      '-p',
      destination.path,
      'zarma_corpus/test/2+3.wav',
    ]);
    expect(result.exitCode, 0);
    expect(result.stdout as String, 'audio-identique');
  });

  test('CRC-32 correspond à la valeur de référence', () {
    expect(crc32(utf8.encode('123456789')), 0xcbf43926);
  });
}
