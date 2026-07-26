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

/// Opération reconnue et son résultat (story 6.1).
///
/// Champ **optionnel** de la réponse : `null` pour un énoncé « nombre seul »,
/// c'est-à-dire tout le comportement des epics 1–5.
///
/// Aucun calcul n'a lieu côté mobile : le résultat vient du serveur, qui le
/// tient de `zarma_numbers` — source unique. Quand l'opération est comprise
/// mais que sa réponse sort du domaine (résultat négatif, dépassement, division
/// par zéro), [result] est `null` et [refusalCode] dit pourquoi. Rien n'est
/// arrondi ni deviné à l'affichage (FR21).
class RecognizedExpression {
  const RecognizedExpression({
    required this.left,
    required this.operator,
    required this.right,
    required this.zarmaText,
    this.result,
    this.remainder = 0,
    this.resultZarmaText = '',
    this.refusalCode,
  });

  factory RecognizedExpression.fromLiveJson(Map<String, dynamic> json) {
    final Object? left = json['left'];
    final Object? operator = json['operator'];
    final Object? right = json['right'];
    final Object? zarmaText = json['zarma_text'];
    final Object? result = json['result'];
    final Object? remainder = json['remainder'];
    final Object? resultZarmaText = json['result_zarma_text'];
    final Object? refusalCode = json['refusal_code'];

    if (left is! num ||
        right is! num ||
        operator is! String ||
        !_operators.contains(operator) ||
        zarmaText is! String ||
        (result != null && result is! num) ||
        (remainder != null && remainder is! num) ||
        (resultZarmaText != null && resultZarmaText is! String) ||
        (refusalCode != null && refusalCode is! String)) {
      throw const RecognitionContractException();
    }
    // Un refus et un résultat ne peuvent pas coexister : ce serait un contrat
    // ambigu, donc un risque d'afficher un nombre là où le serveur refuse.
    if (result != null && refusalCode != null) {
      throw const RecognitionContractException();
    }

    return RecognizedExpression(
      left: left.toInt(),
      operator: operator,
      right: right.toInt(),
      zarmaText: zarmaText,
      result: (result as num?)?.toInt(),
      remainder: (remainder as num?)?.toInt() ?? 0,
      resultZarmaText: resultZarmaText as String? ?? '',
      refusalCode: refusalCode as String?,
    );
  }

  /// Parseur tolérant, réservé aux entrées historiques.
  factory RecognizedExpression.fromJson(Map<String, dynamic> json) {
    return RecognizedExpression(
      left: (json['left'] as num?)?.toInt() ?? 0,
      operator: json['operator'] as String? ?? '+',
      right: (json['right'] as num?)?.toInt() ?? 0,
      zarmaText: json['zarma_text'] as String? ?? '',
      result: (json['result'] as num?)?.toInt(),
      remainder: (json['remainder'] as num?)?.toInt() ?? 0,
      resultZarmaText: json['result_zarma_text'] as String? ?? '',
      refusalCode: json['refusal_code'] as String?,
    );
  }

  static const Set<String> _operators = <String>{'+', '-', '*', '/'};

  final int left;
  final String operator;
  final int right;
  final String zarmaText;
  final int? result;
  final int remainder;
  final String resultZarmaText;
  final String? refusalCode;

  /// Le serveur a-t-il pu répondre ?
  bool get answered => result != null;

  /// Le résultat comporte-t-il un reste de division (« 20 reste 3 ») ?
  bool get hasRemainder => remainder != 0;
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
    this.expression,
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
      expression: json['expression'] is Map<String, dynamic>
          ? RecognizedExpression.fromJson(
              json['expression'] as Map<String, dynamic>)
          : null,
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
    final Object? expressionRaw = json['expression'];
    final Object? latencyTotal = json['latency_total_ms'];
    final Object? latencyAsr = json['latency_asr_ms'];

    if (expressionRaw != null && expressionRaw is! Map<String, dynamic>) {
      throw const RecognitionContractException();
    }

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

    final RecognizedExpression? expression = expressionRaw == null
        ? null
        : RecognizedExpression.fromLiveJson(
            expressionRaw as Map<String, dynamic>);

    final Decision decision = _liveDecision(decisionRaw);
    // Un `accept` doit porter quelque chose de montrable — un nombre, ou une
    // opération. Sans cela l'écran n'aurait rien à afficher (ni à prononcer).
    if (decision == Decision.accept &&
        ((number == null && expression == null) || zarmaText.trim().isEmpty)) {
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
      expression: expression,
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

  /// Opération reconnue, `null` pour un énoncé « nombre seul » (story 6.1).
  final RecognizedExpression? expression;
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
