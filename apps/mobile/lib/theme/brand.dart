/// Palette et thème de marque ZarmaIA / PTR Niger.
///
/// Les teintes viennent du logo lui-même (`tool/build_brand_assets.py` les a
/// mesurées dessus) — l'application doit se reconnaître au premier coup d'œil
/// comme le produit du logo, pas comme un thème Material générique.
library;

import 'package:flutter/material.dart';

abstract final class BrandColors {
  /// Bleu nuit du logo — fonds d'AppBar, pied de page, texte sur fond clair.
  static const Color navy = Color(0xFF071A44);
  static const Color navyDeep = Color(0xFF040F2B);

  /// Bleu d'action — boutons et éléments interactifs (bon contraste au blanc).
  static const Color blue = Color(0xFF0A6CD6);
  static const Color blueLight = Color(0xFF00C8F8);

  /// Rouge du logo — alertes, refus, accents.
  static const Color red = Color(0xFFE00008);

  static const Color surface = Color(0xFFF4F7FC);
}

ThemeData buildBrandTheme() {
  const ColorScheme scheme = ColorScheme(
    brightness: Brightness.light,
    primary: BrandColors.blue,
    onPrimary: Colors.white,
    secondary: BrandColors.red,
    onSecondary: Colors.white,
    tertiary: BrandColors.blueLight,
    onTertiary: BrandColors.navy,
    error: BrandColors.red,
    onError: Colors.white,
    surface: Colors.white,
    onSurface: BrandColors.navy,
  );

  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: BrandColors.surface,
    appBarTheme: const AppBarTheme(
      backgroundColor: Colors.transparent,
      foregroundColor: Colors.white,
      elevation: 0,
      centerTitle: false,
      titleTextStyle: TextStyle(
        color: Colors.white,
        fontSize: 22,
        fontWeight: FontWeight.w700,
      ),
      iconTheme: IconThemeData(color: Colors.white),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: BrandColors.blue,
        foregroundColor: Colors.white,
        textStyle: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: BrandColors.navy,
        side: const BorderSide(color: BrandColors.blue, width: 2),
        textStyle: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      ),
    ),
    cardTheme: CardThemeData(
      elevation: 2,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
    ),
  );
}

/// Dégradé signature de l'AppBar et du pied de page — même teintes partout.
const LinearGradient brandGradient = LinearGradient(
  begin: Alignment.topLeft,
  end: Alignment.bottomRight,
  colors: <Color>[BrandColors.navyDeep, BrandColors.navy, BrandColors.blue],
);
