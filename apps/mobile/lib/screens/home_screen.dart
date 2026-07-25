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
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Semantics(
              button: true,
              label: 'Démarrer un enregistrement audio',
              child: ExcludeSemantics(
                child: SizedBox(
                  width: 240,
                  height: 96,
                  child: FilledButton.icon(
                    key: const Key('start-recording-button'),
                    onPressed: () =>
                        Navigator.of(context).pushNamed(AppRoutes.recording),
                    icon: const Icon(Icons.mic, size: 40),
                    label: const Text('Enregistrer un nombre'),
                  ),
                ),
              ),
            ),
            const SizedBox(height: 16),
            SizedBox(
              height: 48,
              child: TextButton.icon(
                key: const Key('open-history-button'),
                onPressed: () =>
                    Navigator.of(context).pushNamed(AppRoutes.history),
                icon: const Icon(Icons.history),
                label: const Text('Historique'),
              ),
            ),
            const SizedBox(height: 8),
            SizedBox(
              height: 48,
              child: OutlinedButton.icon(
                key: const Key('open-contribution-button'),
                onPressed: () =>
                    Navigator.of(context).pushNamed(AppRoutes.contribute),
                icon: const Icon(Icons.volunteer_activism_outlined),
                label: const Text('Contribuer ma voix'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
