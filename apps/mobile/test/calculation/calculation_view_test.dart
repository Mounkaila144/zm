import 'package:flutter_test/flutter_test.dart';
import 'package:zarma_mobile/calculation/calculation_view.dart';
import 'package:zarma_mobile/models/recognition_result.dart';

/// Présentation d'une opération : trois états, et **jamais** de quatrième
/// « à peu près ». Le mobile ne calcule rien — il choisit quoi montrer.
void main() {
  group('résultat exact', () {
    const RecognizedExpression exact = RecognizedExpression(
      left: 23,
      operator: '+',
      right: 15,
      zarmaText: 'waranka cindi hinza tonton iwey cindi gou',
      result: 38,
      resultZarmaText: 'waranza cindi hakou',
    );

    test('affiche l’opération et son résultat', () {
      const CalculationView view = CalculationView(exact);
      expect(view.outcome, CalculationOutcome.answered);
      expect(view.operationLabel, '23 + 15');
      expect(view.resultLabel, '38');
      expect(view.resultZarmaText, 'waranza cindi hakou');
    });

    test('l’énoncé accessible porte le nombre ET sa forme zarma', () {
      const CalculationView view = CalculationView(exact);
      expect(view.semanticsLabel, contains('23 + 15'));
      expect(view.semanticsLabel, contains('38'));
      expect(view.semanticsLabel, contains('waranza cindi hakou'));
    });
  });

  group('division avec reste', () {
    const RecognizedExpression withRemainder = RecognizedExpression(
      left: 103,
      operator: '/',
      right: 5,
      zarmaText: '—',
      result: 20,
      remainder: 3,
      resultZarmaText: 'waranka ga cindi hinza',
    );

    test('le reste est affiché, jamais arrondi ni supprimé', () {
      const CalculationView view = CalculationView(withRemainder);
      expect(view.outcome, CalculationOutcome.remainder);
      expect(view.resultLabel, '20 reste 3');
      expect(view.operationLabel, '103 ÷ 5');
    });

    test('l’énoncé accessible annonce le reste', () {
      const CalculationView view = CalculationView(withRemainder);
      expect(view.semanticsLabel, contains('reste 3'));
    });
  });

  group('refus', () {
    RecognizedExpression refused(String code) => RecognizedExpression(
          left: 3,
          operator: '-',
          right: 5,
          zarmaText: 'ihinza zabou igou',
          refusalCode: code,
        );

    test('aucun nombre n’est affiché quand le serveur refuse', () {
      final CalculationView view = CalculationView(refused('NEGATIVE_RESULT'));
      expect(view.outcome, CalculationOutcome.refused);
      expect(view.resultLabel, isNull);
    });

    test('chaque code de refus a un message compréhensible', () {
      const Map<String, String> expected = <String, String>{
        'NEGATIVE_RESULT': 'négatif',
        'RESULT_OVERFLOW': '99 999 999 999',
        'DIVISION_BY_ZERO': 'zéro',
        'OPERAND_OUT_OF_RANGE': 'dehors',
      };
      expected.forEach((String code, String fragment) {
        expect(CalculationView(refused(code)).refusalMessage,
            contains(fragment));
      });
    });

    test('un code inconnu reste un refus, pas un résultat', () {
      final CalculationView view = CalculationView(refused('SOMETHING_NEW'));
      expect(view.outcome, CalculationOutcome.refused);
      expect(view.refusalMessage, isNotEmpty);
      expect(view.resultLabel, isNull);
    });
  });

  test('les quatre opérateurs ont un symbole lisible', () {
    const Map<String, String> symbols = <String, String>{
      '+': '+',
      '-': '−',
      '*': '×',
      '/': '÷',
    };
    symbols.forEach((String wire, String shown) {
      final CalculationView view = CalculationView(
        RecognizedExpression(
          left: 4,
          operator: wire,
          right: 2,
          zarmaText: '—',
          result: 2,
        ),
      );
      expect(view.operationLabel, '4 $shown 2');
    });
  });
}
