import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zarma_mobile/calculation/calculation_view.dart';
import 'package:zarma_mobile/models/recognition_result.dart';
import 'package:zarma_mobile/speech/zarma_speaker.dart';
import 'package:zarma_mobile/widgets/brand_app_bar.dart';
import 'package:zarma_mobile/widgets/brand_footer.dart';

/// Pause entre deux répétitions du résultat — assez courte pour qu'une
/// personne qui n'a pas entendu la première fois n'ait pas à réenregistrer.
const Duration calculationRepeatDelay = Duration(seconds: 2);

/// Écran de calcul : l'opération entendue et sa réponse (story 6.1).
///
/// Widget **déclaratif** : la décision d'affichage vient de [CalculationView],
/// le calcul vient du serveur, et l'assemblage audio de [ZarmaSpeaker]. Rien
/// n'est recalculé, arrondi ni recomposé ici.
///
/// Le résultat est **prononcé en boucle** dès l'affichage, toutes les deux
/// secondes : l'utilisateur cible ne lit pas, et peut ne pas regarder l'écran
/// au moment exact où le résultat est dit une première fois.
class CalculationScreen extends ConsumerStatefulWidget {
  const CalculationScreen({super.key, required this.result});

  final RecognitionResult result;

  @override
  ConsumerState<CalculationScreen> createState() => _CalculationScreenState();
}

class _CalculationScreenState extends ConsumerState<CalculationScreen> {
  bool _loopStarted = false;
  int _loopVersion = 0;
  Timer? _repeatTimer;
  Completer<void>? _delayCompleter;
  SpeechOutcome? _lastOutcome;

  Future<void> _speakLoop(
    CalculationView view,
    ZarmaSpeaker speaker,
    int version,
  ) async {
    while (mounted && version == _loopVersion) {
      final SpeechOutcome outcome = await speaker.speak(view.utterance);
      if (!mounted || version != _loopVersion) {
        return;
      }
      setState(() => _lastOutcome = outcome);
      if (outcome == SpeechOutcome.incomplete) {
        return; // rien à répéter : un silence en boucle n'aiderait personne
      }
      await _waitBeforeRepeating();
    }
  }

  Future<void> _waitBeforeRepeating() {
    final Completer<void> completer = Completer<void>();
    _delayCompleter = completer;
    _repeatTimer = Timer(calculationRepeatDelay, () {
      if (!completer.isCompleted) {
        completer.complete();
      }
    });
    return completer.future;
  }

  void _stopLoop() {
    _loopVersion++;
    _repeatTimer?.cancel();
    _repeatTimer = null;
    final Completer<void>? completer = _delayCompleter;
    _delayCompleter = null;
    if (completer != null && !completer.isCompleted) {
      completer.complete();
    }
  }

  @override
  void dispose() {
    _stopLoop();
    super.dispose();
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

    // Dès que la banque est prête, l'énoncé est dit — puis répété en boucle.
    final ZarmaSpeaker? speaker = ref.watch(zarmaSpeakerProvider);
    if (!_loopStarted && speaker != null) {
      _loopStarted = true;
      final int version = ++_loopVersion;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && version == _loopVersion) {
          unawaited(_speakLoop(view, speaker, version));
        }
      });
    }

    return Scaffold(
      key: const Key('calculation-screen'),
      appBar: const BrandAppBar(
        title: 'Calcul',
        automaticallyImplyLeading: false,
      ),
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
    ];
  }
}
