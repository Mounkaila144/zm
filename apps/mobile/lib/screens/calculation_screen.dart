import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zarma_mobile/calculation/calculation_view.dart';
import 'package:zarma_mobile/models/recognition_result.dart';
import 'package:zarma_mobile/speech/zarma_speaker.dart';

/// Écran de calcul : l'opération entendue et sa réponse (story 6.1).
///
/// Widget **déclaratif** : la décision d'affichage vient de [CalculationView],
/// le calcul vient du serveur, et l'assemblage audio de [ZarmaSpeaker]. Rien
/// n'est recalculé, arrondi ni recomposé ici.
///
/// Le résultat est **prononcé dès l'affichage** : l'utilisateur cible ne lit
/// pas, l'écran seul ne lui apprendrait rien. Le seul bouton relance ensuite
/// le parcours vocal pour une nouvelle opération.
class CalculationScreen extends ConsumerStatefulWidget {
  const CalculationScreen({super.key, required this.result});

  final RecognitionResult result;

  @override
  ConsumerState<CalculationScreen> createState() => _CalculationScreenState();
}

class _CalculationScreenState extends ConsumerState<CalculationScreen> {
  bool _spokenOnce = false;
  SpeechOutcome? _lastOutcome;

  Future<void> _speak(CalculationView view) async {
    final ZarmaSpeaker? speaker = ref.read(zarmaSpeakerProvider);
    if (speaker == null) {
      return; // banque pas encore chargée : le déclencheur automatique repassera
    }
    final SpeechOutcome outcome = await speaker.speak(view.utterance);
    if (mounted) {
      setState(() => _lastOutcome = outcome);
    }
  }

  @override
  Widget build(BuildContext context) {
    final RecognizedExpression? expression = widget.result.expression;
    if (expression == null) {
      // Ne devrait pas arriver : la route ne mène ici qu'avec une opération.
      return const Scaffold(
        key: Key('calculation-screen-empty'),
        body: Center(child: Text('Aucune opération à afficher.')),
      );
    }

    final CalculationView view = CalculationView(expression);
    final TextTheme textTheme = Theme.of(context).textTheme;

    // Dès que la banque est prête, l'énoncé est dit — une seule fois.
    if (!_spokenOnce && ref.watch(zarmaSpeakerProvider) != null) {
      _spokenOnce = true;
      WidgetsBinding.instance.addPostFrameCallback((_) => _speak(view));
    }

    return Scaffold(
      key: const Key('calculation-screen'),
      appBar: AppBar(
        title: const Text('Calcul'),
        automaticallyImplyLeading: false,
      ),
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
                    label: view.semanticsLabel,
                    child: ExcludeSemantics(
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: <Widget>[
                          Text(
                            view.operationLabel,
                            key: const Key('calculation-operation'),
                            style: textTheme.headlineMedium,
                            textAlign: TextAlign.center,
                          ),
                          const SizedBox(height: 8),
                          Text(
                            expression.zarmaText,
                            key: const Key('calculation-operation-zarma'),
                            style: textTheme.titleMedium,
                            textAlign: TextAlign.center,
                          ),
                          const Divider(height: 40),
                          ..._answerWidgets(view, textTheme),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
              if (_lastOutcome == SpeechOutcome.incomplete)
                Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: Text(
                    'La voix n’est pas disponible pour cet énoncé.',
                    key: const Key('calculation-speech-unavailable'),
                    style: textTheme.bodySmall,
                    textAlign: TextAlign.center,
                  ),
                ),
              SizedBox(
                height: 88,
                child: FilledButton.icon(
                  key: const Key('record-new-calculation-button'),
                  onPressed: () => Navigator.of(context).pop(),
                  icon: const Icon(Icons.mic, size: 40),
                  label: const Text('Nouvelle opération'),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  List<Widget> _answerWidgets(CalculationView view, TextTheme textTheme) {
    if (view.outcome == CalculationOutcome.refused) {
      return <Widget>[
        const Icon(Icons.block_outlined, size: 48),
        const SizedBox(height: 12),
        Text(
          view.refusalMessage,
          key: const Key('calculation-refusal'),
          style: textTheme.titleMedium,
          textAlign: TextAlign.center,
        ),
      ];
    }
    return <Widget>[
      Text(
        view.resultLabel!,
        key: const Key('calculation-result'),
        style: textTheme.displayLarge,
        textAlign: TextAlign.center,
      ),
      const SizedBox(height: 8),
      Text(
        view.resultZarmaText,
        key: const Key('calculation-result-zarma'),
        style: textTheme.headlineSmall,
        textAlign: TextAlign.center,
      ),
    ];
  }
}
