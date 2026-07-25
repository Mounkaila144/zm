import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zarma_mobile/correction/correction_controller.dart';
import 'package:zarma_mobile/correction/zarma_generator_repository.dart';
import 'package:zarma_mobile/feedback/feedback_controller.dart';
import 'package:zarma_mobile/feedback/feedback_models.dart';
import 'package:zarma_mobile/models/recognition_result.dart';
import 'package:zarma_mobile/navigation/app_routes.dart';
import 'package:zarma_mobile/widgets/number_keypad.dart';
import 'package:zarma_mobile/widgets/zarma_number_display.dart';

/// Correction manuelle : l'utilisateur saisit le bon nombre, voit sa forme
/// zarma canonique (générée par le moteur via l'API) et envoie la correction en
/// feedback `corrected`. Aucune génération ni borne recalculée côté client.
class CorrectionScreen extends ConsumerStatefulWidget {
  const CorrectionScreen({super.key, required this.result});

  final RecognitionResult result;

  @override
  ConsumerState<CorrectionScreen> createState() => _CorrectionScreenState();
}

class _CorrectionScreenState extends ConsumerState<CorrectionScreen> {
  final TextEditingController _textController = TextEditingController();

  @override
  void dispose() {
    _textController.dispose();
    super.dispose();
  }

  Future<void> _submit(ZarmaGeneration generation) async {
    final FeedbackResponse? response =
        await ref.read(feedbackControllerProvider.notifier).submit(
              recognition: widget.result,
              feedbackType: FeedbackType.corrected,
              proposedNumber: widget.result.recognizedNumber,
              correctedNumber: generation.number,
            );
    if (response == null || !mounted) {
      return;
    }
    Navigator.of(context).pushReplacementNamed(
      AppRoutes.result,
      arguments: ConfirmedResult(
        recognition: widget.result,
        number: generation.number,
        zarmaText: generation.zarmaText,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final CorrectionState correction = ref.watch(correctionControllerProvider);
    final FeedbackState feedback = ref.watch(feedbackControllerProvider);
    final bool busy = feedback.isBusy;
    final ZarmaGeneration? ready = correction.ready;

    return Scaffold(
      key: const Key('correction-screen'),
      appBar: AppBar(title: const Text('Correction')),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              Text(
                'Saisissez le bon nombre.',
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.titleLarge,
              ),
              const SizedBox(height: 16),
              NumberKeypad(
                controller: _textController,
                enabled: !busy,
                onChanged: (String value) => ref
                    .read(correctionControllerProvider.notifier)
                    .onInputChanged(value),
              ),
              const SizedBox(height: 24),
              Expanded(
                child: Center(
                  child: _GenerationView(generation: correction.generation),
                ),
              ),
              if (busy)
                const Padding(
                  padding: EdgeInsets.only(bottom: 12),
                  child: LinearProgressIndicator(
                    key: Key('correction-progress-indicator'),
                  ),
                ),
              FilledButton.icon(
                key: const Key('submit-correction-button'),
                onPressed:
                    (ready == null || busy) ? null : () => _submit(ready),
                icon: const Icon(Icons.check),
                label: const Text('Valider la correction'),
              ),
              _feedbackError(feedback, busy, ready),
            ],
          ),
        ),
      ),
    );
  }

  Widget _feedbackError(
    FeedbackState feedback,
    bool busy,
    ZarmaGeneration? ready,
  ) {
    if (feedback.status != FeedbackStatus.error || feedback.failure == null) {
      return const SizedBox.shrink();
    }
    final String message = feedback.failure!.message;
    return Padding(
      padding: const EdgeInsets.only(top: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Semantics(
            liveRegion: true,
            label: message,
            child: Text(
              message,
              key: const Key('correction-feedback-error'),
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.titleSmall,
            ),
          ),
          const SizedBox(height: 8),
          OutlinedButton.icon(
            key: const Key('correction-feedback-retry'),
            onPressed: (ready == null || busy) ? null : () => _submit(ready),
            icon: const Icon(Icons.refresh),
            label: const Text('Réessayer'),
          ),
        ],
      ),
    );
  }
}

/// Affiche l'état de génération de la forme zarma (idle/chargement/donnée/erreur).
class _GenerationView extends StatelessWidget {
  const _GenerationView({required this.generation});

  final AsyncValue<ZarmaGeneration>? generation;

  @override
  Widget build(BuildContext context) {
    final AsyncValue<ZarmaGeneration>? value = generation;
    if (value == null) {
      return Text(
        'La forme zarma s’affichera ici.',
        key: const Key('correction-idle'),
        textAlign: TextAlign.center,
        style: Theme.of(context).textTheme.bodyMedium,
      );
    }
    return value.when(
      loading: () => const CircularProgressIndicator(
        key: Key('correction-generating-indicator'),
      ),
      data: (ZarmaGeneration data) => Semantics(
        liveRegion: true,
        label: 'Nombre ${data.number}. En zarma : ${data.zarmaText}.',
        child: ExcludeSemantics(
          child: Theme(
            data: Theme.of(context).copyWith(
              textTheme: Theme.of(context).textTheme.copyWith(
                    titleLarge: Theme.of(context).textTheme.displaySmall,
                    bodyMedium: Theme.of(context).textTheme.headlineSmall,
                  ),
            ),
            child: ZarmaNumberDisplay(
              number: data.number,
              zarmaText: data.zarmaText,
            ),
          ),
        ),
      ),
      error: (Object error, _) {
        final String message = error is GenerationFailure
            ? error.message
            : 'Impossible de générer la forme zarma pour le moment.';
        return Semantics(
          liveRegion: true,
          label: message,
          child: Text(
            message,
            key: const Key('correction-range-error'),
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.titleSmall?.copyWith(
                  color: Theme.of(context).colorScheme.error,
                ),
          ),
        );
      },
    );
  }
}
