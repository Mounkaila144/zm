import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zarma_mobile/navigation/app_routes.dart';
import 'package:zarma_mobile/recording/audio_recording_models.dart';
import 'package:zarma_mobile/recording/recording_controller.dart';

class RecordingScreen extends ConsumerStatefulWidget {
  const RecordingScreen({super.key});

  @override
  ConsumerState<RecordingScreen> createState() => _RecordingScreenState();
}

class _RecordingScreenState extends ConsumerState<RecordingScreen>
    with WidgetsBindingObserver {
  bool _allowPop = false;
  bool _processingScheduled = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      final RecordingController controller =
          ref.read(recordingControllerProvider.notifier);
      if (ref.read(recordingControllerProvider).phase == RecordingPhase.idle) {
        unawaited(controller.start());
      }
    });
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
        ref.read(recordingControllerProvider.notifier).onAppResumed(),
      );
    }
  }

  Future<void> _cancelAndClose(RecordingController controller) async {
    await controller.cancel();
    if (mounted) {
      setState(() => _allowPop = true);
      Navigator.of(context).pop();
    }
  }

  Future<void> _openProcessing(
    RecordingController controller,
    AudioHandoff handoff,
  ) async {
    await Navigator.of(context).pushNamed(
      AppRoutes.processing,
      arguments: handoff,
    );
    if (!mounted) {
      return;
    }
    _processingScheduled = false;
    if (ref.read(recordingControllerProvider).phase == RecordingPhase.idle) {
      unawaited(controller.start());
    }
  }

  @override
  Widget build(BuildContext context) {
    final RecordingState recording = ref.watch(recordingControllerProvider);
    final RecordingController controller = ref.read(
      recordingControllerProvider.notifier,
    );

    if (recording.phase == RecordingPhase.ready &&
        recording.handoff != null &&
        !_processingScheduled) {
      _processingScheduled = true;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) {
          unawaited(
            _openProcessing(controller, recording.handoff!),
          );
        }
      });
    }

    return PopScope<Object?>(
      canPop: _allowPop,
      onPopInvokedWithResult: (bool didPop, Object? result) {
        if (!didPop) {
          _cancelAndClose(controller);
        }
      },
      child: Scaffold(
        key: const Key('recording-screen'),
        appBar: AppBar(
          title: const Text('Enregistrement'),
          automaticallyImplyLeading: false,
        ),
        body: SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                const Text(
                  'Dites votre calcul.',
                  textAlign: TextAlign.center,
                  style: TextStyle(fontSize: 20, fontWeight: FontWeight.w600),
                ),
                const SizedBox(height: 24),
                Expanded(
                  child: Center(
                    child: SingleChildScrollView(
                      child: _RecordingContent(
                        state: recording,
                        onStart: controller.start,
                        onStop: controller.stop,
                        onOpenSettings: controller.openSettings,
                        onRefreshPermission: controller.refreshPermission,
                      ),
                    ),
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

class _RecordingContent extends StatelessWidget {
  const _RecordingContent({
    required this.state,
    required this.onStart,
    required this.onStop,
    required this.onOpenSettings,
    required this.onRefreshPermission,
  });

  final RecordingState state;
  final VoidCallback onStart;
  final VoidCallback onStop;
  final VoidCallback onOpenSettings;
  final VoidCallback onRefreshPermission;

  @override
  Widget build(BuildContext context) {
    switch (state.phase) {
      case RecordingPhase.idle:
        return _StatusPanel(
          icon: Icons.mic_none,
          message:
              state.message ?? 'Appuyez sur le micro quand vous êtes prêt.',
          action: _LargeAction(
            key: const Key('begin-recording-button'),
            semanticLabel: 'Démarrer l’enregistrement',
            icon: Icons.mic,
            label: 'Démarrer',
            onPressed: onStart,
          ),
        );
      case RecordingPhase.requestingPermission:
        return const _StatusPanel(
          icon: Icons.shield_outlined,
          message: 'Vérification de l’accès au micro…',
          progress: true,
        );
      case RecordingPhase.permissionDenied:
        return _StatusPanel(
          icon: Icons.mic_off_outlined,
          message: state.message!,
          action: _LargeAction(
            key: const Key('retry-permission-button'),
            semanticLabel: 'Réessayer l’autorisation du micro',
            icon: Icons.refresh,
            label: 'Réessayer',
            onPressed: onStart,
          ),
        );
      case RecordingPhase.permissionPermanentlyDenied:
        return _StatusPanel(
          icon: Icons.settings_outlined,
          message: state.message!,
          action: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              _LargeAction(
                key: const Key('open-settings-button'),
                semanticLabel: 'Ouvrir les réglages du micro',
                icon: Icons.settings,
                label: 'Ouvrir les réglages',
                onPressed: onOpenSettings,
              ),
              const SizedBox(height: 12),
              TextButton.icon(
                key: const Key('refresh-permission-button'),
                onPressed: onRefreshPermission,
                icon: const Icon(Icons.refresh),
                label: const Text('J’ai autorisé le micro'),
              ),
            ],
          ),
        );
      case RecordingPhase.recording:
        return _ActiveRecording(
          state: state,
          onStop: onStop,
        );
      case RecordingPhase.validating:
        return _StatusPanel(
          icon: Icons.graphic_eq,
          message: state.message ?? 'Vérification de l’audio…',
          progress: true,
        );
      case RecordingPhase.ready:
        return const _StatusPanel(
          icon: Icons.check_circle_outline,
          message: 'Enregistrement terminé. Traitement en cours…',
          progress: true,
        );
      case RecordingPhase.invalid:
        return _StatusPanel(
          icon: Icons.warning_amber_rounded,
          message: state.message!,
          action: _LargeAction(
            key: const Key('retry-recording-button'),
            semanticLabel: 'Recommencer l’enregistrement',
            icon: Icons.replay,
            label: 'Recommencer',
            onPressed: onStart,
          ),
        );
      case RecordingPhase.error:
        return _StatusPanel(
          icon: Icons.error_outline,
          message: state.message!,
          action: _LargeAction(
            key: const Key('retry-recording-button'),
            semanticLabel: 'Réessayer l’enregistrement',
            icon: Icons.refresh,
            label: 'Réessayer',
            onPressed: onStart,
          ),
        );
    }
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
    return Column(
      children: <Widget>[
        Semantics(
          liveRegion: true,
          label: 'Micro actif. ${_formatDuration(state.elapsed)}. '
              'Niveau audio $percentage pour cent.',
          child: ExcludeSemantics(
            child: Column(
              children: <Widget>[
                Icon(
                  Icons.mic,
                  key: const Key('active-microphone-icon'),
                  size: 72,
                  color: Theme.of(context).colorScheme.error,
                ),
                const SizedBox(height: 16),
                Text(
                  _formatDuration(state.elapsed),
                  key: const Key('recording-timer'),
                  style: Theme.of(context).textTheme.displaySmall,
                ),
                const SizedBox(height: 24),
                LinearProgressIndicator(
                  key: const Key('audio-level-indicator'),
                  value: state.level,
                  minHeight: 16,
                  borderRadius: BorderRadius.circular(8),
                ),
                const SizedBox(height: 16),
                Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: <Widget>[
                    Icon(
                      state.isApproachingLimit
                          ? Icons.timer_off_outlined
                          : Icons.timer_outlined,
                    ),
                    const SizedBox(width: 8),
                    Flexible(
                      child: Text(
                        state.isApproachingLimit
                            ? 'Limite proche : arrêt automatique à 10 secondes.'
                            : 'Zone idéale : entre 1 et 8 secondes.',
                        key: const Key('recording-limit-message'),
                        textAlign: TextAlign.center,
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 24),
        _LargeAction(
          key: const Key('stop-recording-button'),
          semanticLabel: 'Arrêter l’enregistrement',
          icon: Icons.stop,
          label: 'Arrêter',
          onPressed: onStop,
        ),
      ],
    );
  }
}

class _StatusPanel extends StatelessWidget {
  const _StatusPanel({
    required this.icon,
    required this.message,
    this.action,
    this.progress = false,
  });

  final IconData icon;
  final String message;
  final Widget? action;
  final bool progress;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: <Widget>[
        Semantics(
          liveRegion: true,
          label: message,
          child: ExcludeSemantics(
            child: Column(
              children: <Widget>[
                Icon(icon, size: 72),
                const SizedBox(height: 16),
                Text(
                  message,
                  key: const Key('recording-status-message'),
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.bodyLarge,
                ),
                if (progress) ...<Widget>[
                  const SizedBox(height: 24),
                  const CircularProgressIndicator(),
                ],
              ],
            ),
          ),
        ),
        if (action != null) ...<Widget>[
          const SizedBox(height: 24),
          action!,
        ],
      ],
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
    const ButtonStyle style = ButtonStyle(
      minimumSize: WidgetStatePropertyAll<Size>(
        Size.fromHeight(52),
      ),
    );
    final Widget button = FilledButton.icon(
      onPressed: onPressed,
      style: style,
      icon: Icon(icon),
      label: Text(label),
    );
    return Semantics(
      button: true,
      label: semanticLabel,
      child: ExcludeSemantics(child: button),
    );
  }
}

String _formatDuration(Duration duration) {
  final int seconds = duration.inSeconds;
  final int tenths = (duration.inMilliseconds % 1000) ~/ 100;
  return '00:${seconds.toString().padLeft(2, '0')}.$tenths';
}
