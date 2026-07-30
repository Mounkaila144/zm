import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:tts_recorder/zip_writer.dart';

void main() {
  test('le ZIP Piper conserve les octets des masters', () async {
    final directory = await Directory.systemTemp.createTemp('tts-zip-');
    addTearDown(() => directory.delete(recursive: true));
    final destination = File('${directory.path}/dataset.zip');
    final master = Uint8List.fromList(<int>[1, 2, 3, 4, 5]);

    await writeStoredZip(destination, <ZipEntrySource>[
      ZipEntrySource.fromFile(
        'zarma_tts/voix/wavs/tts_1.wav',
        await File('${directory.path}/tts_1.wav').writeAsBytes(master),
      ),
      ZipEntrySource.fromBytes(
        'zarma_tts/voix/metadata.csv',
        Uint8List.fromList(utf8.encode('tts_1.wav|afo\n')),
      ),
    ]);

    final result = await Process.run('unzip', <String>[
      '-p',
      destination.path,
      'zarma_tts/voix/wavs/tts_1.wav',
    ]);
    expect(result.exitCode, 0);
    expect((result.stdout as String).codeUnits, master);
  });
}
