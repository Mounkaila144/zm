import 'package:flutter/material.dart';
import 'package:zarma_mobile/feedback/feedback_models.dart';
import 'package:zarma_mobile/models/recognition_result.dart';
import 'package:zarma_mobile/navigation/app_routes.dart';
import 'package:zarma_mobile/widgets/brand_app_bar.dart';
import 'package:zarma_mobile/widgets/brand_footer.dart';
import 'package:zarma_mobile/widgets/zarma_number_display.dart';

class ResultScreen extends StatelessWidget {
  const ResultScreen({super.key, required this.result, this.confirmed});

  /// Reconnaissance d'origine (décision serveur inchangée).
  final RecognitionResult result;

  /// Choix confirmé en 3.4 : le nombre/forme retenus peuvent différer de la
  /// proposition principale (alternative choisie). `null` sur le chemin `accept`.
  final ConfirmedResult? confirmed;

  int? get _number => confirmed?.number ?? result.recognizedNumber;

  String get _zarmaText => confirmed?.zarmaText ?? result.zarmaText;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      key: const Key('result-screen'),
      appBar: const BrandAppBar(title: 'Résultat'),
      bottomNavigationBar: const BrandFooter(),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              Expanded(
                child: Center(
                  child: Semantics(
                    liveRegion: true,
                    label: 'Nombre reconnu $_number. '
                        'En zarma : $_zarmaText.',
                    child: ExcludeSemantics(
                      child: Theme(
                        data: Theme.of(context).copyWith(
                          textTheme: Theme.of(context).textTheme.copyWith(
                                titleLarge:
                                    Theme.of(context).textTheme.displayLarge,
                                bodyMedium:
                                    Theme.of(context).textTheme.headlineMedium,
                              ),
                        ),
                        child: ZarmaNumberDisplay(number: _number),
                      ),
                    ),
                  ),
                ),
              ),
              FilledButton.icon(
                key: const Key('record-new-number-button'),
                onPressed: () => Navigator.of(context).pop(),
                icon: const Icon(Icons.mic),
                label: const Text('Enregistrer un nouveau nombre'),
              ),
              const SizedBox(height: 12),
              OutlinedButton.icon(
                key: const Key('open-correction-button'),
                onPressed: () => Navigator.of(context).pushNamed(
                  AppRoutes.correction,
                  arguments: result,
                ),
                icon: const Icon(Icons.edit_outlined),
                label: const Text('Corriger'),
              ),
              const SizedBox(height: 12),
              TextButton.icon(
                key: const Key('result-home-button'),
                onPressed: () => Navigator.of(context).popUntil(
                  (Route<dynamic> route) => route.isFirst,
                ),
                icon: const Icon(Icons.home_outlined),
                label: const Text('Retour à l’Accueil'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
