/// Présentation d'une opération reconnue — logique **hors widget** (story 6.1).
///
/// L'écran de calcul ne décide rien : il affiche ce que cette classe expose.
/// Aucun calcul n'a lieu ici non plus — le résultat vient du serveur, qui le
/// tient de `zarma_numbers`. Ce fichier ne fait que **choisir quoi montrer**,
/// et c'est pour cela qu'il est testable sans monter d'interface.
///
/// Trois états, et seulement trois :
///
/// | État        | Quand                                    | Ce qui s'affiche          |
/// |-------------|------------------------------------------|---------------------------|
/// | `answered`  | résultat exact                           | le nombre + sa forme zarma |
/// | `remainder` | division non entière                     | quotient **et** reste      |
/// | `refused`   | hors domaine (négatif, dépassement, ÷ 0) | la raison, jamais un nombre |
///
/// Il n'existe volontairement pas de quatrième état « à peu près » : un
/// résultat approché serait indétectable pour un utilisateur qui ne lit pas
/// (FR21/NFR14).
library;

import 'package:zarma_mobile/models/recognition_result.dart';
import 'package:zarma_mobile/speech/voice_bank.dart';

enum CalculationOutcome { answered, remainder, refused }

class CalculationView {
  const CalculationView(this.expression);

  final RecognizedExpression expression;

  CalculationOutcome get outcome {
    if (!expression.answered) {
      return CalculationOutcome.refused;
    }
    return expression.hasRemainder
        ? CalculationOutcome.remainder
        : CalculationOutcome.answered;
  }

  /// L'opération en chiffres, lisible d'un coup d'œil (« 23 + 15 »).
  String get operationLabel =>
      '${expression.left} $_operatorLabel ${expression.right}';

  String get _operatorLabel {
    switch (expression.operator) {
      case '+':
        return '+';
      case '-':
        return '−';
      case '*':
        return '×';
      case '/':
        return '÷';
      default:
        return expression.operator;
    }
  }

  /// Le résultat en chiffres, ou `null` si le serveur a refusé de répondre.
  String? get resultLabel {
    if (!expression.answered) {
      return null;
    }
    return expression.hasRemainder
        ? '${expression.result} reste ${expression.remainder}'
        : '${expression.result}';
  }

  /// Forme zarma du résultat — c'est **elle** qui sera prononcée.
  String get resultZarmaText => expression.resultZarmaText;

  /// Message de refus, formulé sans jargon et sans jamais suggérer un nombre.
  String get refusalMessage {
    switch (expression.refusalCode) {
      case 'NEGATIVE_RESULT':
        return 'Cette soustraction donnerait un nombre négatif : '
            'il n’y a pas de réponse à dire.';
      case 'RESULT_OVERFLOW':
        return 'Le résultat dépasse 99 999 999 999 : il ne peut pas être dit.';
      case 'DIVISION_BY_ZERO':
        return 'On ne peut pas diviser par zéro.';
      case 'OPERAND_OUT_OF_RANGE':
        return 'Un des deux nombres est en dehors de ce que l’application sait dire.';
      default:
        return 'Cette opération n’a pas de réponse que l’application sache dire.';
    }
  }

  /// Ce que l'application doit **dire** — la seule sortie qui atteigne la cible.
  ///
  /// Un refus se prononce par sa consigne enregistrée : se taire serait
  /// indistinguable d'une panne pour quelqu'un qui ne lit pas (AC4/FR21). Un
  /// résultat se prononce depuis la forme zarma renvoyée par le serveur — jamais
  /// recomposée ici.
  List<VoiceSegment> get utterance {
    if (outcome == CalculationOutcome.refused) {
      return refusalUtterance();
    }
    return utteranceFromZarma(resultZarmaText);
  }

  /// Énoncé destiné aux lecteurs d'écran (et modèle de la restitution vocale).
  String get semanticsLabel {
    final String operation = 'Opération $operationLabel.';
    switch (outcome) {
      case CalculationOutcome.refused:
        return '$operation $refusalMessage';
      case CalculationOutcome.remainder:
        return '$operation Résultat ${expression.result}, '
            'reste ${expression.remainder}. En zarma : $resultZarmaText.';
      case CalculationOutcome.answered:
        return '$operation Résultat ${expression.result}. '
            'En zarma : $resultZarmaText.';
    }
  }
}
