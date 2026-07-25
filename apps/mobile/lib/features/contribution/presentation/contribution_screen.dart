import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zarma_mobile/features/contribution/application/contribution_controller.dart';
import 'package:zarma_mobile/features/contribution/models/contribution_models.dart';
import 'package:zarma_mobile/recording/audio_recording_models.dart';

class ContributionScreen extends ConsumerStatefulWidget {
  const ContributionScreen({super.key});

  @override
  ConsumerState<ContributionScreen> createState() => _ContributionScreenState();
}

class _ContributionScreenState extends ConsumerState<ContributionScreen>
    with WidgetsBindingObserver {
  bool _allowPop = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      unawaited(
        ref.read(contributionControllerProvider.notifier).onAppResumed(),
      );
    }
  }

  Future<void> _cancelAndClose(ContributionController controller) async {
    await controller.cancelFlow();
    if (mounted) {
      setState(() => _allowPop = true);
      Navigator.of(context).pop();
    }
  }

  Future<void> _showWithdrawalConfirmation(
    ContributionController controller,
  ) async {
    final bool? confirmed = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (BuildContext context) {
        return AlertDialog(
          key: const Key('withdrawal-confirmation-dialog'),
          title: const Text('Retirer mes contributions ?'),
          content: const Text(
            'Tous les audios consentis seront supprimés et les métadonnées '
            'seront anonymisées. Cette action est irréversible.',
          ),
          actions: <Widget>[
            TextButton(
              key: const Key('cancel-withdrawal-button'),
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text('Conserver'),
            ),
            FilledButton(
              key: const Key('confirm-withdrawal-button'),
              onPressed: () => Navigator.of(context).pop(true),
              style: FilledButton.styleFrom(
                backgroundColor: Theme.of(context).colorScheme.error,
                foregroundColor: Theme.of(context).colorScheme.onError,
              ),
              child: const Text('Retirer définitivement'),
            ),
          ],
        );
      },
    );
    if (!mounted) {
      return;
    }
    if (confirmed == true) {
      await controller.confirmWithdrawal();
    } else {
      controller.dismissWithdrawal();
    }
  }

  @override
  Widget build(BuildContext context) {
    final ContributionState state = ref.watch(contributionControllerProvider);
    final ContributionController controller =
        ref.read(contributionControllerProvider.notifier);
    ref.listen<ContributionState>(contributionControllerProvider, (
      ContributionState? previous,
      ContributionState next,
    ) {
      if (next.withdrawalPhase == ContributionWithdrawalPhase.confirmation &&
          previous?.withdrawalPhase !=
              ContributionWithdrawalPhase.confirmation) {
        unawaited(_showWithdrawalConfirmation(controller));
      }
    });

    return PopScope<Object?>(
      canPop: _allowPop,
      onPopInvokedWithResult: (bool didPop, Object? result) {
        if (!didPop) {
          unawaited(_cancelAndClose(controller));
        }
      },
      child: Scaffold(
        key: const Key('contribution-screen'),
        appBar: AppBar(title: const Text('Contribuer')),
        body: SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(24, 16, 24, 24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                Expanded(
                  child: Center(
                    child: SingleChildScrollView(
                      child: _ContributionContent(
                        state: state,
                        controller: controller,
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 16),
                Semantics(
                  button: true,
                  label: 'Retirer définitivement mes contributions',
                  child: SizedBox(
                    height: 52,
                    child: TextButton.icon(
                      key: const Key('request-withdrawal-button'),
                      onPressed: state.withdrawalPhase ==
                              ContributionWithdrawalPhase.withdrawing
                          ? null
                          : controller.requestWithdrawal,
                      style: TextButton.styleFrom(
                        foregroundColor: Theme.of(context).colorScheme.error,
                      ),
                      icon: const Icon(Icons.delete_forever_outlined),
                      label: const Text('Retirer mes contributions'),
                    ),
                  ),
                ),
                const SizedBox(height: 8),
                SizedBox(
                  height: 52,
                  child: OutlinedButton.icon(
                    key: const Key('cancel-contribution-button'),
                    onPressed: () => _cancelAndClose(controller),
                    icon: const Icon(Icons.close),
                    label: const Text('Annuler'),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _ContributionContent extends StatelessWidget {
  const _ContributionContent({
    required this.state,
    required this.controller,
  });

  final ContributionState state;
  final ContributionController controller;

  @override
  Widget build(BuildContext context) {
    if (state.withdrawalPhase == ContributionWithdrawalPhase.withdrawing) {
      return const _StatusPanel(
        key: Key('contribution-withdrawal-progress'),
        icon: Icons.delete_sweep_outlined,
        message: 'Suppression sécurisée de vos contributions…',
        progress: true,
      );
    }
    if (state.withdrawalPhase == ContributionWithdrawalPhase.error) {
      return _StatusPanel(
        key: const Key('contribution-withdrawal-error'),
        icon: Icons.warning_amber_rounded,
        message: state.withdrawalMessage ??
            'Le retrait n’a pas pu être terminé. Réessayez.',
        action: _LargeAction(
          key: const Key('retry-withdrawal-button'),
          semanticLabel: 'Réessayer le retrait des contributions',
          icon: Icons.refresh,
          label: 'Réessayer',
          onPressed: controller.retryWithdrawal,
        ),
      );
    }
    if (state.withdrawalPhase == ContributionWithdrawalPhase.success) {
      return const _StatusPanel(
        key: Key('contribution-withdrawal-success'),
        icon: Icons.check_circle_outline,
        message: 'Vos contributions ont été retirées.',
      );
    }
    if (state.phase == ContributionPhase.loadingPrompt ||
        state.phase == ContributionPhase.inactive) {
      return const _StatusPanel(
        key: Key('contribution-prompt-loading'),
        icon: Icons.format_list_numbered,
        message: 'Préparation du nombre à prononcer…',
        progress: true,
      );
    }
    if (state.phase == ContributionPhase.error && state.prompt == null) {
      return _StatusPanel(
        key: const Key('contribution-prompt-error'),
        icon: Icons.cloud_off_outlined,
        message: state.message ?? 'Impossible de proposer un nombre.',
        action: _LargeAction(
          key: const Key('retry-contribution-prompt-button'),
          semanticLabel: 'Réessayer de charger un nombre',
          icon: Icons.refresh,
          label: 'Réessayer',
          onPressed: controller.loadNextPrompt,
        ),
      );
    }
    if (state.phase == ContributionPhase.sending) {
      return const _StatusPanel(
        key: Key('contribution-upload-sending'),
        icon: Icons.cloud_upload_outlined,
        message: 'Envoi sécurisé de la contribution…',
        progress: true,
      );
    }
    if (state.phase == ContributionPhase.success) {
      return _StatusPanel(
        key: const Key('contribution-upload-success'),
        icon: Icons.check_circle_outline,
        message: state.message ?? 'Contribution envoyée. Merci !',
        action: _LargeAction(
          key: const Key('continue-after-contribution-button'),
          semanticLabel: 'Prononcer un nouveau nombre',
          icon: Icons.arrow_forward,
          label: 'Continuer',
          onPressed: controller.continueAfterSuccess,
        ),
      );
    }
    if (state.phase == ContributionPhase.uploadError) {
      return _StatusPanel(
        key: const Key('contribution-upload-error'),
        icon: Icons.cloud_off_outlined,
        message: state.message ?? 'La contribution n’a pas pu être envoyée.',
        action: _LargeAction(
          key: const Key('retry-contribution-after-upload-button'),
          semanticLabel: 'Réenregistrer la contribution',
          icon: Icons.replay,
          label: 'Réenregistrer',
          onPressed: controller.restartRecording,
        ),
      );
    }

    final ContributionPrompt prompt = state.prompt!;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Semantics(
          header: true,
          child: Text(
            'Prononcez ce nombre',
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.titleLarge,
          ),
        ),
        const SizedBox(height: 12),
        Text(
          _formatNumber(prompt.expectedNumber),
          key: const Key('contribution-expected-number'),
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.displayMedium,
        ),
        const SizedBox(height: 8),
        Text(
          prompt.expectedPrompt,
          key: const Key('contribution-expected-prompt'),
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.headlineSmall,
        ),
        const SizedBox(height: 32),
        _RecordingStep(state: state, controller: controller),
      ],
    );
  }
}

class _RecordingStep extends StatelessWidget {
  const _RecordingStep({
    required this.state,
    required this.controller,
  });

  final ContributionState state;
  final ContributionController controller;

  @override
  Widget build(BuildContext context) {
    final RecordingState recording = state.recording;
    if (state.phase == ContributionPhase.audioReady) {
      return _StatusPanel(
        key: const Key('contribution-audio-ready'),
        icon: Icons.check_circle_outline,
        message: 'Audio prêt pour la prochaine étape.',
        action: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            _LargeAction(
              key: const Key('submit-contribution-button'),
              semanticLabel: 'Envoyer la contribution',
              icon: Icons.cloud_upload,
              label: 'Envoyer',
              onPressed: controller.submitPending,
            ),
            const SizedBox(height: 12),
            OutlinedButton.icon(
              key: const Key('restart-contribution-recording-button'),
              onPressed: controller.restartRecording,
              icon: const Icon(Icons.replay),
              label: const Text('Recommencer'),
            ),
          ],
        ),
      );
    }

    switch (recording.phase) {
      case RecordingPhase.idle:
        return _PromptReadyActions(controller: controller);
      case RecordingPhase.requestingPermission:
        return const _StatusPanel(
          icon: Icons.shield_outlined,
          message: 'Vérification de l’accès au micro…',
          progress: true,
        );
      case RecordingPhase.permissionDenied:
        return _StatusPanel(
          icon: Icons.mic_off_outlined,
          message: recording.message ?? 'Le micro est nécessaire.',
          action: _LargeAction(
            key: const Key('retry-contribution-permission-button'),
            semanticLabel: 'Réessayer l’autorisation du micro',
            icon: Icons.refresh,
            label: 'Réessayer',
            onPressed: controller.startRecording,
          ),
        );
      case RecordingPhase.permissionPermanentlyDenied:
        return _StatusPanel(
          icon: Icons.settings_outlined,
          message: recording.message ?? 'Autorisez le micro dans les réglages.',
          action: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              _LargeAction(
                key: const Key('open-contribution-settings-button'),
                semanticLabel: 'Ouvrir les réglages du micro',
                icon: Icons.settings,
                label: 'Ouvrir les réglages',
                onPressed: controller.openSettings,
              ),
              TextButton.icon(
                key: const Key('refresh-contribution-permission-button'),
                onPressed: controller.refreshPermission,
                icon: const Icon(Icons.refresh),
                label: const Text('J’ai autorisé le micro'),
              ),
            ],
          ),
        );
      case RecordingPhase.recording:
        return _ActiveRecording(
          state: recording,
          onStop: controller.stopRecording,
        );
      case RecordingPhase.validating:
        return const _StatusPanel(
          icon: Icons.graphic_eq,
          message: 'Vérification de l’audio…',
          progress: true,
        );
      case RecordingPhase.ready:
        return const _StatusPanel(
          icon: Icons.graphic_eq,
          message: 'Préparation du brouillon…',
          progress: true,
        );
      case RecordingPhase.invalid:
      case RecordingPhase.error:
        return _StatusPanel(
          icon: Icons.warning_amber_rounded,
          message: recording.message ?? 'L’enregistrement a échoué.',
          action: _LargeAction(
            key: const Key('retry-contribution-recording-button'),
            semanticLabel: 'Recommencer l’enregistrement',
            icon: Icons.replay,
            label: 'Recommencer',
            onPressed: controller.startRecording,
          ),
        );
    }
  }
}

class _PromptReadyActions extends StatelessWidget {
  const _PromptReadyActions({required this.controller});

  final ContributionController controller;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        _LargeAction(
          key: const Key('begin-contribution-recording-button'),
          semanticLabel: 'Démarrer l’enregistrement consenti',
          icon: Icons.mic,
          label: 'Enregistrer',
          onPressed: controller.startRecording,
        ),
        const SizedBox(height: 12),
        TextButton.icon(
          key: const Key('skip-contribution-prompt-button'),
          onPressed: controller.loadNextPrompt,
          icon: const Icon(Icons.skip_next),
          label: const Text('Un autre nombre'),
        ),
      ],
    );
  }
}

class _ActiveRecording extends StatelessWidget {
  const _ActiveRecording({
    required this.state,
    required this.onStop,
  });

  final RecordingState state;
  final VoidCallback onStop;

  @override
  Widget build(BuildContext context) {
    final int percentage = (state.level * 100).round();
    return Semantics(
      liveRegion: true,
      label: 'Micro actif. ${_formatDuration(state.elapsed)}. '
          'Niveau audio $percentage pour cent.',
      child: Column(
        children: <Widget>[
          Icon(
            Icons.mic,
            key: const Key('contribution-active-microphone'),
            size: 72,
            color: Theme.of(context).colorScheme.error,
          ),
          const SizedBox(height: 12),
          Text(
            _formatDuration(state.elapsed),
            key: const Key('contribution-recording-timer'),
            style: Theme.of(context).textTheme.displaySmall,
          ),
          const SizedBox(height: 16),
          LinearProgressIndicator(
            key: const Key('contribution-audio-level'),
            value: state.level,
            minHeight: 16,
            borderRadius: BorderRadius.circular(8),
          ),
          const SizedBox(height: 20),
          _LargeAction(
            key: const Key('stop-contribution-recording-button'),
            semanticLabel: 'Arrêter l’enregistrement',
            icon: Icons.stop,
            label: 'Arrêter',
            onPressed: onStop,
          ),
        ],
      ),
    );
  }
}

class _StatusPanel extends StatelessWidget {
  const _StatusPanel({
    super.key,
    required this.icon,
    required this.message,
    this.progress = false,
    this.action,
  });

  final IconData icon;
  final String message;
  final bool progress;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      liveRegion: true,
      child: Column(
        children: <Widget>[
          Icon(icon, size: 56),
          const SizedBox(height: 12),
          Text(message, textAlign: TextAlign.center),
          if (progress) ...<Widget>[
            const SizedBox(height: 20),
            const CircularProgressIndicator(),
          ],
          if (action != null) ...<Widget>[
            const SizedBox(height: 20),
            action!,
          ],
        ],
      ),
    );
  }
}

class _LargeAction extends StatelessWidget {
  const _LargeAction({
    super.key,
    required this.semanticLabel,
    required this.icon,
    required this.label,
    required this.onPressed,
  });

  final String semanticLabel;
  final IconData icon;
  final String label;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: semanticLabel,
      child: ExcludeSemantics(
        child: SizedBox(
          height: 56,
          child: FilledButton.icon(
            onPressed: onPressed,
            icon: Icon(icon),
            label: Text(label),
          ),
        ),
      ),
    );
  }
}

String _formatDuration(Duration duration) {
  final int seconds = duration.inSeconds;
  final int tenths = (duration.inMilliseconds.remainder(1000) ~/ 100);
  return '${seconds.toString().padLeft(2, '0')}:$tenths';
}

String _formatNumber(int number) {
  final String digits = number.toString();
  final StringBuffer buffer = StringBuffer();
  for (int index = 0; index < digits.length; index++) {
    if (index > 0 && (digits.length - index) % 3 == 0) {
      buffer.write(' ');
    }
    buffer.write(digits[index]);
  }
  return buffer.toString();
}
