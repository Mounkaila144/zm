import 'package:flutter/material.dart';
import 'package:zarma_mobile/navigation/app_routes.dart';

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      key: const Key('home-screen'),
      appBar: AppBar(title: const Text('Accueil')),
      body: Center(
        child: Semantics(
          button: true,
          label: 'Démarrer un enregistrement audio',
          child: ExcludeSemantics(
            child: SizedBox(
              width: 240,
              height: 120,
              child: FilledButton.icon(
                key: const Key('start-recording-button'),
                onPressed: () =>
                    Navigator.of(context).pushNamed(AppRoutes.recording),
                icon: const Icon(Icons.mic, size: 56),
                label: const Text('Enregistrer'),
                style: FilledButton.styleFrom(
                  textStyle: Theme.of(context).textTheme.titleLarge,
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
