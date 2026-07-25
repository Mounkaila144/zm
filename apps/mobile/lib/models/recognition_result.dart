/// Modèle partagé des réponses `/recognize` et `/history`.
library;

enum Decision { accept, confirm, repeat }

class RecognitionContractException implements Exception {
  const RecognitionContractException();
}

class RecognitionAlternative {
  const RecognitionAlternative({
    required this.number,
    required this.zarmaText,
    required this.score,
  });

  factory RecognitionAlternative.fromLiveJson(Map<String, dynamic> json) {
    final Object? number = json['number'];
    final Object? zarmaText = json['zarma_text'];
    final Object? score = json['score'];
    if ((number != null && number is! num) ||
        zarmaText is! String ||
        score is! num ||
        score < 0 ||
        score > 1) {
      throw const RecognitionContractException();
    }
    return RecognitionAlternative(
      number: (number as num?)?.toInt(),
      zarmaText: zarmaText,
      score: score.toDouble(),
    );
  }

  final int? number;
  final String zarmaText;
  final double score;
}

class RecognitionResult {
  const RecognitionResult({
    required this.id,
    required this.recognizedNumber,
    required this.zarmaText,
    required this.normalizedText,
    required this.confidence,
    required this.decision,
    required this.modelVersion,
    required this.grammarVersion,
    this.alternatives = const <RecognitionAlternative>[],
    this.latencyTotalMs = 0,
    this.latencyAsrMs = 0,
    this.createdAt,
  });

  /// Parseur tolérant réservé aux entrées historiques existantes.
  factory RecognitionResult.fromJson(Map<String, dynamic> json) {
    final Object? createdAtRaw = json['created_at'];
    final Object? alternativesRaw = json['alternatives'];
    return RecognitionResult(
      id: json['id'] as String? ?? '',
      recognizedNumber: (json['recognized_number'] as num?)?.toInt(),
      zarmaText: json['zarma_text'] as String? ?? '',
      normalizedText: json['normalized_text'] as String? ?? '',
      confidence: (json['confidence'] as num?)?.toDouble() ?? 0,
      decision: _historyDecision(json['decision']),
      alternatives: alternativesRaw is List<dynamic>
          ? alternativesRaw
              .whereType<Map<String, dynamic>>()
              .map(_tolerantAlternative)
              .toList(growable: false)
          : const <RecognitionAlternative>[],
      modelVersion: json['model_version'] as String? ?? '',
      grammarVersion: json['grammar_version'] as String? ?? '',
      latencyTotalMs: (json['latency_total_ms'] as num?)?.toInt() ?? 0,
      latencyAsrMs: (json['latency_asr_ms'] as num?)?.toInt() ?? 0,
      createdAt:
          createdAtRaw is String ? DateTime.tryParse(createdAtRaw) : null,
    );
  }

  /// Parseur strict pour une réponse live `200` de `/recognize`.
  factory RecognitionResult.fromLiveJson(Map<String, dynamic> json) {
    final Object? id = json['id'];
    final Object? number = json['recognized_number'];
    final Object? zarmaText = json['zarma_text'];
    final Object? normalizedText = json['normalized_text'];
    final Object? confidence = json['confidence'];
    final Object? decisionRaw = json['decision'];
    final Object? alternativesRaw = json['alternatives'];
    final Object? modelVersion = json['model_version'];
    final Object? grammarVersion = json['grammar_version'];
    final Object? latencyTotal = json['latency_total_ms'];
    final Object? latencyAsr = json['latency_asr_ms'];

    if (id is! String ||
        id.isEmpty ||
        (number != null && number is! num) ||
        zarmaText is! String ||
        normalizedText is! String ||
        confidence is! num ||
        confidence < 0 ||
        confidence > 1 ||
        decisionRaw is! String ||
        alternativesRaw is! List<dynamic> ||
        modelVersion is! String ||
        modelVersion.isEmpty ||
        grammarVersion is! String ||
        grammarVersion.isEmpty ||
        latencyTotal is! num ||
        latencyTotal < 0 ||
        latencyAsr is! num ||
        latencyAsr < 0) {
      throw const RecognitionContractException();
    }

    final Decision decision = _liveDecision(decisionRaw);
    if (decision == Decision.accept &&
        (number == null || zarmaText.trim().isEmpty)) {
      throw const RecognitionContractException();
    }

    final List<RecognitionAlternative> alternatives =
        alternativesRaw.map((dynamic item) {
      if (item is! Map<String, dynamic>) {
        throw const RecognitionContractException();
      }
      return RecognitionAlternative.fromLiveJson(item);
    }).toList(growable: false);

    return RecognitionResult(
      id: id,
      recognizedNumber: (number as num?)?.toInt(),
      zarmaText: zarmaText,
      normalizedText: normalizedText,
      confidence: confidence.toDouble(),
      decision: decision,
      alternatives: alternatives,
      modelVersion: modelVersion,
      grammarVersion: grammarVersion,
      latencyTotalMs: latencyTotal.toInt(),
      latencyAsrMs: latencyAsr.toInt(),
    );
  }

  final String id;
  final int? recognizedNumber;
  final String zarmaText;
  final String normalizedText;
  final double confidence;
  final Decision decision;
  final List<RecognitionAlternative> alternatives;
  final String modelVersion;
  final String grammarVersion;
  final int latencyTotalMs;
  final int latencyAsrMs;
  final DateTime? createdAt;
}

Decision _liveDecision(String value) {
  switch (value) {
    case 'accept':
      return Decision.accept;
    case 'confirm':
      return Decision.confirm;
    case 'repeat':
      return Decision.repeat;
    default:
      throw const RecognitionContractException();
  }
}

Decision _historyDecision(Object? value) {
  if (value == 'accept') {
    return Decision.accept;
  }
  if (value == 'repeat') {
    return Decision.repeat;
  }
  return Decision.confirm;
}

RecognitionAlternative _tolerantAlternative(Map<String, dynamic> json) {
  return RecognitionAlternative(
    number: (json['number'] as num?)?.toInt(),
    zarmaText: json['zarma_text'] as String? ?? '',
    score: (json['score'] as num?)?.toDouble() ?? 0,
  );
}
