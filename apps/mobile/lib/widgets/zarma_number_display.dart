import 'package:flutter/material.dart';

/// Affiche un nombre reconnu : chiffres + forme zarma (partagé entre écrans).
///
/// Widget purement présentatif — aucune logique numérique. `zarmaText` et
/// `number` proviennent de l'API.
class ZarmaNumberDisplay extends StatelessWidget {
  const ZarmaNumberDisplay({
    super.key,
    required this.zarmaText,
    this.number,
  });

  final String zarmaText;
  final int? number;

  @override
  Widget build(BuildContext context) {
    final TextTheme textTheme = Theme.of(context).textTheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Text(
          number?.toString() ?? '—',
          style: textTheme.titleLarge,
        ),
        if (zarmaText.isNotEmpty)
          Text(
            zarmaText,
            style: textTheme.bodyMedium,
          ),
      ],
    );
  }
}
