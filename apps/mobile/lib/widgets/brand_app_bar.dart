import 'package:flutter/material.dart';
import 'package:zarma_mobile/theme/brand.dart';

/// AppBar de marque, identique sur tous les écrans.
class BrandAppBar extends StatelessWidget implements PreferredSizeWidget {
  const BrandAppBar({
    super.key,
    required this.title,
    this.automaticallyImplyLeading = true,
  });

  final String title;
  final bool automaticallyImplyLeading;

  @override
  Size get preferredSize => const Size.fromHeight(kToolbarHeight);

  @override
  Widget build(BuildContext context) {
    return AppBar(
      automaticallyImplyLeading: automaticallyImplyLeading,
      backgroundColor: BrandColors.navyDeep,
      surfaceTintColor: Colors.transparent,
      flexibleSpace: const DecoratedBox(
        decoration: BoxDecoration(gradient: brandGradient),
      ),
      title: _BrandTitle(
        title: title,
        useLogoColors: title == 'ZarmaIA',
      ),
    );
  }
}

class _BrandTitle extends StatelessWidget {
  const _BrandTitle({
    required this.title,
    required this.useLogoColors,
  });

  final String title;
  final bool useLogoColors;

  @override
  Widget build(BuildContext context) {
    final Text text = Text(
      title,
      overflow: TextOverflow.ellipsis,
      style: Theme.of(context).appBarTheme.titleTextStyle,
    );
    if (!useLogoColors) {
      return text;
    }
    return ShaderMask(
      blendMode: BlendMode.srcIn,
      shaderCallback: (Rect bounds) => const LinearGradient(
        colors: <Color>[BrandColors.blueLight, BrandColors.red],
        stops: <double>[0.58, 0.76],
      ).createShader(bounds),
      child: text,
    );
  }
}
