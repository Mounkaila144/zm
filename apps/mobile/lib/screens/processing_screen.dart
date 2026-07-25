import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zarma_mobile/models/recognition_result.dart';
import 'package:zarma_mobile/navigation/app_routes.dart';
import 'package:zarma_mobile/recognition/recognition_controller.dart';
import 'package:zarma_mobile/recording/audio_recording_models.dart';

class ProcessingScreen extends ConsumerStatefulWidget {
  const ProcessingScreen({super.key, required this.handoff});

  final AudioHandoff handoff;

  @override
  ConsumerState<ProcessingScreen> createState() => _ProcessingScreenState();
}

class _ProcessingScreenState extends ConsumerState<ProcessingScreen> {
  bool _navigationScheduled = false;

  @override
  void initState() {
    super.initState();
    Future<void>.microtask(() {
      if (mounted) {
        return ref
            .read(recognitionControllerProvider(widget.handoff).notifier)
            .start();
      }
    });
  }

  void _reactToState(RecognitionState next) {
    if (!mounted || _navigationScheduled) {
      return;
    }
    if (next.phase == RecognitionPhase.cancelled) {
      _navigationScheduled = true;
      Navigator.of(context).pop();
      return;
    }
    if (next.phase != RecognitionPhase.success || next.result == null) {
      return;
    }
    _navigationScheduled = true;
    final RecognitionResult result = next.result!;
    final String destination = result.decision == Decision.accept
        ? AppRoutes.result
        : AppRoutes.confirmation;
    Navigator.of(context).pushReplacementNamed(
      destination,
      arguments: result,
    );
  }

  @override
  Widget build(BuildContext context) {
    final provider = recognitionControllerProvider(widget.handoff);
    ref.listen<RecognitionState>(provider, (_, RecognitionState next) {
      _reactToState(next);
    });
    final RecognitionState state = ref.watch(provider);
    final RecognitionController controller = ref.read(provider.notifier);
    final bool processing = state.phase == RecognitionPhase.initial ||
        state.phase == RecognitionPhase.processing;

    return PopScope<Object?>(
      canPop: !processing,
      onPopInvokedWithResult: (bool didPop, Object? result) {
        if (!didPop && processing) {
          unawaited(controller.cancel());
        }
      },
      child: Scaffold(
        key: const Key('processing-screen'),
        appBar: AppBar(title: const Text('Traitement')),
        body: SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Center(
              child: processing
                  ? _ProcessingBody(
                      onCancel: () => controller.cancel(),
                    )
                  : _FailureBody(
                      message: state.failure?.message ??
                          'Le service n’a pas pu traiter la demande.',
                      onRecordAgain: () => Navigator.of(context).pop(),
                      onHome: () => Navigator.of(context).popUntil(
                        (Route<dynamic> route) => route.isFirst,
                      ),
                    ),
            ),
          ),
        ),
      ),
    );
  }
}

class _ProcessingBody extends StatelessWidget {
  const _ProcessingBody({required this.onCancel});

  final Future<void> Function() onCancel;

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Semantics(
          liveRegion: true,
          label: 'Traitement de votre enregistrement en cours.',
          child: const CircularProgressIndicator(
            key: Key('recognition-progress-indicator'),
          ),
        ),
        const SizedBox(height: 24),
        Text(
          'Nous écoutons votre nombre…',
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.titleLarge,
        ),
        const SizedBox(height: 12),
        const Text(
          'Vous pouvez annuler à tout moment.',
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: 32),
        OutlinedButton.icon(
          key: const Key('cancel-recognition-button'),
          onPressed: onCancel,
          icon: const Icon(Icons.close),
          label: const Text('Annuler'),
        ),
      ],
    );
  }
}

class _FailureBody extends StatelessWidget {
  const _FailureBody({
    required this.message,
    required this.onRecordAgain,
    required this.onHome,
  });

  final String message;
  final VoidCallback onRecordAgain;
  final VoidCallback onHome;

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Semantics(
          liveRegion: true,
          label: message,
          child: ExcludeSemantics(
            child: Column(
              children: <Widget>[
                const Icon(Icons.cloud_off_outlined, size: 72),
                const SizedBox(height: 16),
                Text(
                  message,
                  key: const Key('recognition-error-message'),
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.titleMedium,
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 32),
        FilledButton.icon(
          key: const Key('record-again-button'),
          onPressed: onRecordAgain,
          icon: const Icon(Icons.mic),
          label: const Text('Réenregistrer'),
        ),
        const SizedBox(height: 12),
        TextButton.icon(
          key: const Key('processing-home-button'),
          onPressed: onHome,
          icon: const Icon(Icons.home_outlined),
          label: const Text('Retour à l’Accueil'),
        ),
      ],
    );
  }
}
