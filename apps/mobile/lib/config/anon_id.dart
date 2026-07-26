import 'dart:io';
import 'dart:math';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:path_provider/path_provider.dart';

const String _anonIdFileName = 'anonymous-device-id';

/// Génère un identifiant anonyme au format UUID v4 (NFR7 — anonymat).
///
/// Ne dépend d'aucun paquet externe. `random` est injectable pour les tests.
String generateAnonId([Random? random]) {
  final Random rng = random ?? Random.secure();
  final List<int> bytes = List<int>.generate(16, (_) => rng.nextInt(256));
  bytes[6] = (bytes[6] & 0x0f) | 0x40; // version 4
  bytes[8] = (bytes[8] & 0x3f) | 0x80; // variant RFC 4122
  final String hex =
      bytes.map((int b) => b.toRadixString(16).padLeft(2, '0')).join();
  return '${hex.substring(0, 8)}-${hex.substring(8, 12)}-'
      '${hex.substring(12, 16)}-${hex.substring(16, 20)}-${hex.substring(20)}';
}

Future<String> loadOrCreateAnonId() async {
  final Directory supportDirectory = await getApplicationSupportDirectory();
  final File identifierFile = File(
    '${supportDirectory.path}${Platform.pathSeparator}$_anonIdFileName',
  );
  if (await identifierFile.exists()) {
    final String existing = (await identifierFile.readAsString()).trim();
    if (_uuidV4.hasMatch(existing)) {
      return existing;
    }
  }
  final String created = generateAnonId();
  await identifierFile.writeAsString(created, flush: true);
  return created;
}

final RegExp _uuidV4 = RegExp(
  r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
);

/// Identifiant anonyme du device injecté dans les appels API isolés par
/// utilisateur (ex. `/history`). Surchargeable en test via `overrideWithValue`.
///
final Provider<String> anonIdProvider = Provider<String>((ref) {
  return generateAnonId();
});
