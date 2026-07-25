/// Modèles du contrat `/feedback` et argument de présentation d'un choix.
library;

import 'package:zarma_mobile/models/recognition_result.dart';

/// Types de feedback acceptés par l'API (implémentation Pydantic réelle).
enum FeedbackType { confirmed, corrected, rejected, repeatRequested }

extension FeedbackTypeWire on FeedbackType {
  /// Valeur exacte attendue sur le fil par le backend.
  String get wireValue {
    switch (this) {
      case FeedbackType.confirmed:
        return 'confirmed';
      case FeedbackType.corrected:
        return 'corrected';
      case FeedbackType.rejected:
        return 'rejected';
      case FeedbackType.repeatRequested:
        return 'repeat_requested';
    }
  }

  static FeedbackType? fromWire(String value) {
    switch (value) {
      case 'confirmed':
        return FeedbackType.confirmed;
      case 'corrected':
        return FeedbackType.corrected;
      case 'rejected':
        return FeedbackType.rejected;
      case 'repeat_requested':
        return FeedbackType.repeatRequested;
      default:
        return null;
    }
  }
}

/// Réponse `/feedback` mal formée : traitée comme erreur de contrat sûre.
class FeedbackContractException implements Exception {
  const FeedbackContractException();
}

/// Corps exact d'un `POST /feedback`. Ne porte jamais les versions : le backend
/// les hérite de la reconnaissance persistée.
class FeedbackRequest {
  const FeedbackRequest({
    required this.recognitionId,
    required this.anonId,
    required this.feedbackType,
    this.proposedNumber,
    this.correctedNumber,
  });

  final String recognitionId;
  final String anonId;
  final FeedbackType feedbackType;
  final int? proposedNumber;
  final int? correctedNumber;

  Map<String, dynamic> toJson() => <String, dynamic>{
        'recognition_id': recognitionId,
        'anon_id': anonId,
        'feedback_type': feedbackType.wireValue,
        'proposed_number': proposedNumber,
        'corrected_number': correctedNumber,
      };
}

/// Receipt `201` renvoyé par l'API après persistance du feedback.
class FeedbackResponse {
  const FeedbackResponse({
    required this.id,
    required this.recognitionId,
    required this.anonId,
    required this.feedbackType,
    required this.proposedNumber,
    required this.correctedNumber,
    required this.modelVersion,
    required this.grammarVersion,
    required this.createdAt,
  });

  /// Parseur strict : toute divergence de forme devient une erreur de contrat.
  factory FeedbackResponse.fromJson(Map<String, dynamic> json) {
    final Object? id = json['id'];
    final Object? recognitionId = json['recognition_id'];
    final Object? anonId = json['anon_id'];
    final Object? feedbackTypeRaw = json['feedback_type'];
    final Object? proposedNumber = json['proposed_number'];
    final Object? correctedNumber = json['corrected_number'];
    final Object? modelVersion = json['model_version'];
    final Object? grammarVersion = json['grammar_version'];
    final Object? createdAtRaw = json['created_at'];

    if (id is! String ||
        id.isEmpty ||
        recognitionId is! String ||
        recognitionId.isEmpty ||
        anonId is! String ||
        anonId.isEmpty ||
        feedbackTypeRaw is! String ||
        (proposedNumber != null && proposedNumber is! num) ||
        (correctedNumber != null && correctedNumber is! num) ||
        modelVersion is! String ||
        modelVersion.isEmpty ||
        grammarVersion is! String ||
        grammarVersion.isEmpty ||
        createdAtRaw is! String) {
      throw const FeedbackContractException();
    }

    final FeedbackType? feedbackType =
        FeedbackTypeWire.fromWire(feedbackTypeRaw);
    final DateTime? createdAt = DateTime.tryParse(createdAtRaw);
    if (feedbackType == null || createdAt == null) {
      throw const FeedbackContractException();
    }

    return FeedbackResponse(
      id: id,
      recognitionId: recognitionId,
      anonId: anonId,
      feedbackType: feedbackType,
      proposedNumber: (proposedNumber as num?)?.toInt(),
      correctedNumber: (correctedNumber as num?)?.toInt(),
      modelVersion: modelVersion,
      grammarVersion: grammarVersion,
      createdAt: createdAt,
    );
  }

  final String id;
  final String recognitionId;
  final String anonId;
  final FeedbackType feedbackType;
  final int? proposedNumber;
  final int? correctedNumber;
  final String modelVersion;
  final String grammarVersion;
  final DateTime createdAt;
}

/// Argument de présentation typé pour afficher un choix confirmé sur Résultat
/// sans falsifier la décision serveur d'origine (`confirm` reste `confirm`).
class ConfirmedResult {
  const ConfirmedResult({
    required this.recognition,
    required this.number,
    required this.zarmaText,
  });

  final RecognitionResult recognition;
  final int number;
  final String zarmaText;
}
