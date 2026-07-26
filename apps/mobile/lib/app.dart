import 'package:flutter/material.dart';
import 'package:zarma_mobile/navigation/app_routes.dart';
import 'package:zarma_mobile/theme/brand.dart';

class ZarmaApp extends StatelessWidget {
  const ZarmaApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Zarma IA',
      debugShowCheckedModeBanner: false,
      theme: buildBrandTheme(),
      initialRoute: AppRoutes.home,
      routes: AppRoutes.routes,
      onGenerateRoute: AppRoutes.onGenerateRoute,
    );
  }
}
