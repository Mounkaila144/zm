import 'package:flutter/material.dart';
import 'package:zarma_mobile/navigation/app_routes.dart';

class ZarmaApp extends StatelessWidget {
  const ZarmaApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Zarma',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF315C49),
          brightness: Brightness.light,
        ),
        useMaterial3: true,
      ),
      initialRoute: AppRoutes.home,
      routes: AppRoutes.routes,
      onGenerateRoute: AppRoutes.onGenerateRoute,
    );
  }
}
