import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// Champ de saisie numérique de la correction (clavier numérique système).
///
/// Purement présentatif : n'applique que des contraintes de forme (chiffres,
/// longueur max 12). `MAX_VALUE` (99 999 999 999) tient sur 11 chiffres et
/// est **lui-même** le plus grand nombre à 11 chiffres : plafonner ici à 11
/// pile rendrait le contrôle numérique de `CorrectionController` inatteignable
/// (tout ce qui se tape serait automatiquement valide, et un chiffre de plus
/// serait tronqué en silence, sans message). La marge d'un chiffre laisse le
/// contrôle numérique — la vraie règle métier — produire un message clair.
class NumberKeypad extends StatelessWidget {
  const NumberKeypad({
    super.key,
    required this.controller,
    required this.onChanged,
    this.enabled = true,
  });

  final TextEditingController controller;
  final ValueChanged<String> onChanged;
  final bool enabled;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      textField: true,
      label: 'Saisir le nombre correct',
      child: TextField(
        key: const Key('correction-number-field'),
        controller: controller,
        enabled: enabled,
        onChanged: onChanged,
        autofocus: true,
        keyboardType: TextInputType.number,
        textAlign: TextAlign.center,
        style: Theme.of(context).textTheme.displaySmall,
        inputFormatters: <TextInputFormatter>[
          FilteringTextInputFormatter.digitsOnly,
          LengthLimitingTextInputFormatter(12),
        ],
        decoration: const InputDecoration(
          hintText: 'Ex. 235',
          border: OutlineInputBorder(),
        ),
      ),
    );
  }
}
