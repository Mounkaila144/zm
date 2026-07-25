import 'package:flutter_test/flutter_test.dart';
import 'package:zarma_mobile/models/recognition_result.dart';

/// Contrat mobile de l'opération reconnue (story 6.1).
///
/// Deux exigences : le champ est **additif** (une réponse « nombre seul » reste
/// valide et sans expression), et un contrat ambigu est refusé plutôt
/// qu'interprété — afficher un nombre là où le serveur refuse serait la faute
/// la plus grave possible pour un utilisateur qui ne lit pas.
void main() {
  Map<String, dynamic> response({Object? expression}) {
    return <String, dynamic>{
      'id': 'recognition-id',
      'recognized_number': null,
      'zarma_text': 'waranka cindi hinza tonton iwey cindi gou',
      'normalized_text': 'waranka cindi hinza tonton iwey cindi gou',
      'confidence': 0.92,
      'decision': 'accept',
      'alternatives': <dynamic>[],
      'expression': expression,
      'model_version': 'mock-1',
      'grammar_version': '1.3.0',
      'latency_total_ms': 50,
      'latency_asr_ms': 40,
    };
  }

  Map<String, dynamic> expressionJson() {
    return <String, dynamic>{
      'left': 23,
      'operator': '+',
      'right': 15,
      'zarma_text': 'waranka cindi hinza tonton iwey cindi gou',
      'result': 38,
      'remainder': 0,
      'result_zarma_text': 'waranza cindi hakou',
      'refusal_code': null,
    };
  }

  test('mappe une opération complète', () {
    final RecognitionResult result =
        RecognitionResult.fromLiveJson(response(expression: expressionJson()));

    final RecognizedExpression expression = result.expression!;
    expect(expression.left, 23);
    expect(expression.operator, '+');
    expect(expression.right, 15);
    expect(expression.result, 38);
    expect(expression.answered, isTrue);
    expect(expression.hasRemainder, isFalse);
  });

  test('un accept peut ne porter qu’une opération, sans nombre seul', () {
    final RecognitionResult result =
        RecognitionResult.fromLiveJson(response(expression: expressionJson()));
    expect(result.recognizedNumber, isNull);
    expect(result.decision, Decision.accept);
  });

  test('conserve le reste d’une division', () {
    final Map<String, dynamic> json = expressionJson()
      ..['operator'] = '/'
      ..['result'] = 20
      ..['remainder'] = 3
      ..['result_zarma_text'] = 'waranka ga cindi hinza';

    final RecognizedExpression expression =
        RecognitionResult.fromLiveJson(response(expression: json)).expression!;
    expect(expression.remainder, 3);
    expect(expression.hasRemainder, isTrue);
  });

  test('un refus n’a pas de résultat', () {
    final Map<String, dynamic> json = expressionJson()
      ..['result'] = null
      ..['result_zarma_text'] = ''
      ..['refusal_code'] = 'NEGATIVE_RESULT';

    final RecognizedExpression expression =
        RecognitionResult.fromLiveJson(response(expression: json)).expression!;
    expect(expression.answered, isFalse);
    expect(expression.refusalCode, 'NEGATIVE_RESULT');
  });

  test('refuse un contrat où résultat et refus coexistent', () {
    final Map<String, dynamic> json = expressionJson()
      ..['refusal_code'] = 'NEGATIVE_RESULT';

    expect(
      () => RecognitionResult.fromLiveJson(response(expression: json)),
      throwsA(isA<RecognitionContractException>()),
    );
  });

  test('refuse un opérateur inconnu', () {
    final Map<String, dynamic> json = expressionJson()..['operator'] = '%';
    expect(
      () => RecognitionResult.fromLiveJson(response(expression: json)),
      throwsA(isA<RecognitionContractException>()),
    );
  });

  test('refuse une expression mal typée', () {
    expect(
      () => RecognitionResult.fromLiveJson(response(expression: 'oui')),
      throwsA(isA<RecognitionContractException>()),
    );
  });

  test('une réponse sans expression reste valide (non-régression)', () {
    final Map<String, dynamic> json = response()
      ..['recognized_number'] = 42
      ..['zarma_text'] = 'waytaci cindi hinka'
      ..remove('expression');

    final RecognitionResult result = RecognitionResult.fromLiveJson(json);
    expect(result.expression, isNull);
    expect(result.recognizedNumber, 42);
  });
}
