import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:path_provider_platform_interface/path_provider_platform_interface.dart';
import 'package:tts_recorder/app_controller.dart';

import 'support/wav_factory.dart';

class _FakePathProvider extends PathProviderPlatform {
  _FakePathProvider(this.documentsPath);

  final String documentsPath;

  @override
  Future<String?> getApplicationDocumentsPath() async => documentsPath;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test(
    'export produces a directly usable single-speaker Piper dataset',
    () async {
      final temporaryDirectory = await Directory.systemTemp.createTemp(
        'tts-recorder-export-',
      );
      final previousPathProvider = PathProviderPlatform.instance;
      PathProviderPlatform.instance = _FakePathProvider(
        temporaryDirectory.path,
      );

      addTearDown(() async {
        PathProviderPlatform.instance = previousPathProvider;
        await temporaryDirectory.delete(recursive: true);
      });

      final controller = AppController();
      await controller.initialize();
      final speaker = await controller.addSpeaker('Voix test');

      final prompt = controller.selectedPrompts.first;
      final sourceWav = File('${temporaryDirectory.path}/capture.wav');
      await sourceWav.writeAsBytes(
        makePcmWav(sampleRate: 48000, toneSeconds: 0.5, amplitude: 0.12),
      );

      final take = await controller.storeTake(
        speaker: speaker,
        prompt: prompt,
        temporaryPath: sourceWav.path,
        autoStopped: false,
      );

      final zip = await controller.exportSpeaker(speaker);
      expect(await zip.exists(), isTrue);

      final datasetRoot = 'zarma_tts/${speaker.folderName}';
      final listing = await Process.run('unzip', ['-Z1', zip.path]);
      expect(listing.exitCode, 0);
      expect(listing.stdout, contains('$datasetRoot/metadata.csv'));
      expect(listing.stdout, contains('$datasetRoot/manifest.csv'));
      expect(listing.stdout, contains('$datasetRoot/wavs/${take.fileName}'));

      final metadata = await Process.run('unzip', [
        '-p',
        zip.path,
        '$datasetRoot/metadata.csv',
      ]);
      expect(metadata.exitCode, 0);
      expect(metadata.stdout, '${take.fileName}|${prompt.zarmaText}\n');

      final manifest = await Process.run('unzip', [
        '-p',
        zip.path,
        '$datasetRoot/manifest.csv',
      ]);
      expect(manifest.exitCode, 0);
      expect(manifest.stdout, contains(prompt.id));
      expect(manifest.stdout, contains(prompt.zarmaText));
      expect(manifest.stdout, contains(',48000,'));
    },
  );
}
