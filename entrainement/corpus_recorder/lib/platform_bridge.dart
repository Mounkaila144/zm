import 'package:flutter/services.dart';

class PlatformBridge {
  static const _channel = MethodChannel('ne.zarma.corpus_recorder/platform');

  Future<String?> importCsv() => _channel.invokeMethod<String>('importCsv');

  Future<ImportedExampleZip?> importExampleZip(String targetDirectory) async {
    final raw = await _channel.invokeMethod<Map<Object?, Object?>>(
      'importExampleZip',
      <String, Object?>{'targetDirectory': targetDirectory},
    );
    if (raw == null) {
      return null;
    }
    final rawFiles = raw['files']! as Map<Object?, Object?>;
    return ImportedExampleZip(
      manifest: raw['manifest']! as String,
      files: rawFiles.map(
        (name, path) => MapEntry(name! as String, path! as String),
      ),
    );
  }

  Future<void> play(String path) =>
      _channel.invokeMethod<void>('playAudio', <String, Object?>{'path': path});

  Future<void> stopPlayback() => _channel.invokeMethod<void>('stopAudio');
}

class ImportedExampleZip {
  const ImportedExampleZip({required this.manifest, required this.files});

  final String manifest;
  final Map<String, String> files;
}
