import 'package:flutter/material.dart';
import 'package:zarma_mobile/theme/brand.dart';

/// Affiche un nombre reconnu — gros et seul (partagé entre écrans).
///
/// L'utilisateur cible ne lit pas : la forme zarma n'est **jamais** affichée
/// à l'écran, seulement dite (voir `ZarmaSpeaker`). Ce widget ne montre donc
/// que le chiffre, en aussi grand que possible.
class ZarmaNumberDisplay extends StatelessWidget {
  const ZarmaNumberDisplay({super.key, this.number});

  final int? number;

  @override
  Widget build(BuildContext context) {
    return Text(
      number?.toString() ?? '—',
      style: Theme.of(context).textTheme.displayLarge?.copyWith(
            fontWeight: FontWeight.w800,
            color: BrandColors.navy,
          ),
    );
  }
}
