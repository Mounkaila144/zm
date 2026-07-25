import 'package:zarma_mobile/recording/audio_recording_models.dart';

/// Catégories explicites du catalogue afin de rendre sa couverture testable.
enum ContributionPromptCategory {
  unitOrTen,
  composition,
  hundred,
  thousand,
  scaleOrBoundary,
  asrConfusion,
}

/// Nombre à prononcer et forme canonique résolue exclusivement par l'API.
class ContributionPrompt {
  const ContributionPrompt({
    required this.expectedNumber,
    required this.expectedPrompt,
    required this.category,
    required this.grammarVersion,
  });

  final int expectedNumber;
  final String expectedPrompt;
  final ContributionPromptCategory category;
  final String grammarVersion;
}

/// Métadonnées optionnelles, non identifiantes et injectables.
class ContributionMetadata {
  const ContributionMetadata({
    this.region,
    this.deviceInfo,
  });

  final String? region;
  final String? deviceInfo;
}

/// Brouillon local transmis à la future étape d'upload (story 4.3).
///
/// L'audio reste exclusivement référencé par son chemin temporaire dans
/// [AudioHandoff] : aucun byte ni encodage base64 n'est conservé en mémoire.
class PendingContribution {
  const PendingContribution({
    required this.audio,
    required this.expectedNumber,
    required this.expectedPrompt,
    required this.anonId,
    required this.consentId,
    required this.grammarVersion,
    required this.consentVersion,
    this.region,
    this.deviceInfo,
  });

  final AudioHandoff audio;
  final int expectedNumber;
  final String expectedPrompt;
  final String anonId;
  final String consentId;
  final String grammarVersion;
  final String consentVersion;
  final String? region;
  final String? deviceInfo;
}
