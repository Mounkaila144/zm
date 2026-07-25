import 'dart:math';

import 'package:flutter_riverpod/flutter_riverpod.dart';

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

/// Identifiant anonyme du device injecté dans les appels API isolés par
/// utilisateur (ex. `/history`). Surchargeable en test via `overrideWithValue`.
///
/// La persistance durable de cet identifiant relève d'une story de fondation
/// dédiée ; ici il sert de point d'injection unique.
final Provider<String> anonIdProvider = Provider<String>((ref) {
  return generateAnonId();
});
