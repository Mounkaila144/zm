import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// Champ de saisie numérique de la correction (clavier numérique système).
///
/// Purement présentatif : n'applique que des contraintes de forme (chiffres,
/// longueur max 7 = taille de 1 000 000). Aucune règle numérique métier ici.
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
          LengthLimitingTextInputFormatter(7),
        ],
        decoration: const InputDecoration(
          hintText: 'Ex. 235',
          border: OutlineInputBorder(),
        ),
      ),
    );
  }
}
