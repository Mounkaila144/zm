import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zarma_mobile/feedback/feedback_controller.dart';
import 'package:zarma_mobile/feedback/feedback_models.dart';
import 'package:zarma_mobile/models/recognition_result.dart';
import 'package:zarma_mobile/navigation/app_routes.dart';

/// Écran d'ambiguïté. `confirm` présente les propositions du serveur et attend
/// un choix explicite ; `repeat` (ou un `confirm` sans candidat exploitable)
/// n'affiche aucun nombre et invite à réenregistrer. Le mobile ne recalcule ni
/// confiance, ni ordre, ni forme zarma.
class ConfirmationScreen extends ConsumerStatefulWidget {
  const ConfirmationScreen({super.key, required this.result});

  final RecognitionResult result;

  @override
  ConsumerState<ConfirmationScreen> createState() => _ConfirmationScreenState();
}

class _ConfirmationScreenState extends ConsumerState<ConfirmationScreen> {
  Future<void> Function()? _lastAction;

  /// Propositions sélectionnables : proposition principale puis alternatives
  /// dans l'ordre serveur, dédupliquées par nombre, sans null ni forme vide.
  /// Aucun tri côté client.
  List<_Candidate> _candidates() {
    final RecognitionResult result = widget.result;
    final Set<int> seen = <int>{};
    final List<_Candidate> list = <_Candidate>[];

    final int? mainNumber = result.recognizedNumber;
    if (mainNumber != null && result.zarmaText.trim().isNotEmpty) {
      seen.add(mainNumber);
      list.add(
        _Candidate(number: mainNumber, zarmaText: result.zarmaText),
      );
    }
    for (final RecognitionAlternative alternative in result.alternatives) {
      final int? number = alternative.number;
      if (number == null || alternative.zarmaText.trim().isEmpty) {
        continue;
      }
      if (!seen.add(number)) {
        continue;
      }
      list.add(
        _Candidate(number: number, zarmaText: alternative.zarmaText),
      );
    }
    return list;
  }

  Future<void> _confirm(_Candidate candidate) async {
    _lastAction = () => _confirm(candidate);
    final FeedbackResponse? response =
        await ref.read(feedbackControllerProvider.notifier).submit(
              recognition: widget.result,
              feedbackType: FeedbackType.confirmed,
              proposedNumber: candidate.number,
            );
    if (response == null || !mounted) {
      return;
    }
    Navigator.of(context).pushReplacementNamed(
      AppRoutes.result,
      arguments: ConfirmedResult(
        recognition: widget.result,
        number: candidate.number,
        zarmaText: candidate.zarmaText,
      ),
    );
  }

  Future<void> _requestRepeat() async {
    _lastAction = _requestRepeat;
    final FeedbackResponse? response =
        await ref.read(feedbackControllerProvider.notifier).submit(
              recognition: widget.result,
              feedbackType: FeedbackType.repeatRequested,
              proposedNumber: widget.result.recognizedNumber,
            );
    if (response == null || !mounted) {
      return;
    }
    // Retour à l'Enregistrement s'il est encore dans la pile, sinon l'Accueil ;
    // jamais de repassage par Traitement/Confirmation.
    Navigator.of(context).popUntil(
      (Route<dynamic> route) =>
          route.settings.name == AppRoutes.recording || route.isFirst,
    );
  }

  void _openCorrection() {
    // Aucun feedback au simple tap : le choix final n'existe qu'après la
    // saisie/validation de la story 3.5.
    Navigator.of(context).pushNamed(
      AppRoutes.correction,
      arguments: widget.result,
    );
  }

  void _retry() {
    _lastAction?.call();
  }

  @override
  Widget build(BuildContext context) {
    final FeedbackState feedback = ref.watch(feedbackControllerProvider);
    final bool busy = feedback.isBusy;
    final List<_Candidate> candidates = _candidates();
    final bool repeatOnly =
        widget.result.decision == Decision.repeat || candidates.isEmpty;

    return Scaffold(
      key: const Key('confirmation-screen'),
      appBar: AppBar(title: const Text('Confirmation')),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: repeatOnly
              ? _RepeatBody(
                  busy: busy,
                  onRecordAgain: busy ? null : () => _requestRepeat(),
                  error: _errorSection(feedback, busy),
                )
              : _ConfirmBody(
                  candidates: candidates,
                  busy: busy,
                  onSelect: busy ? null : (_Candidate c) => _confirm(c),
                  onRepeat: busy ? null : () => _requestRepeat(),
                  onCorrect: busy ? null : _openCorrection,
                  error: _errorSection(feedback, busy),
                ),
        ),
      ),
    );
  }

  Widget _errorSection(FeedbackState feedback, bool busy) {
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
              key: const Key('feedback-error-message'),
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.titleSmall,
            ),
          ),
          const SizedBox(height: 8),
          OutlinedButton.icon(
            key: const Key('feedback-retry-button'),
            onPressed: busy ? null : _retry,
            icon: const Icon(Icons.refresh),
            label: const Text('Réessayer'),
          ),
        ],
      ),
    );
  }
}

class _Candidate {
  const _Candidate({required this.number, required this.zarmaText});

  final int number;
  final String zarmaText;
}

class _ConfirmBody extends StatelessWidget {
  const _ConfirmBody({
    required this.candidates,
    required this.busy,
    required this.onSelect,
    required this.onRepeat,
    required this.onCorrect,
    required this.error,
  });

  final List<_Candidate> candidates;
  final bool busy;
  final void Function(_Candidate candidate)? onSelect;
  final VoidCallback? onRepeat;
  final VoidCallback? onCorrect;
  final Widget error;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Text(
          'Quel nombre avez-vous dit ?',
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.titleLarge,
        ),
        const SizedBox(height: 4),
        const Text(
          'Choisissez une proposition ou réenregistrez.',
          textAlign: TextAlign.center,
        ),
        if (busy) ...<Widget>[
          const SizedBox(height: 16),
          const LinearProgressIndicator(
            key: Key('feedback-progress-indicator'),
          ),
        ],
        const SizedBox(height: 16),
        Expanded(
          child: ListView.separated(
            itemCount: candidates.length,
            separatorBuilder: (_, __) => const SizedBox(height: 12),
            itemBuilder: (BuildContext context, int index) {
              final _Candidate candidate = candidates[index];
              return _CandidateCard(
                candidate: candidate,
                primary: index == 0,
                onTap: onSelect == null ? null : () => onSelect!(candidate),
              );
            },
          ),
        ),
        const SizedBox(height: 12),
        OutlinedButton.icon(
          key: const Key('request-repeat-button'),
          onPressed: onRepeat,
          icon: const Icon(Icons.mic),
          label: const Text('Aucune : réenregistrer'),
        ),
        const SizedBox(height: 12),
        TextButton.icon(
          key: const Key('open-correction-button'),
          onPressed: onCorrect,
          icon: const Icon(Icons.edit_outlined),
          label: const Text('Saisir moi-même'),
        ),
        error,
      ],
    );
  }
}

class _CandidateCard extends StatelessWidget {
  const _CandidateCard({
    required this.candidate,
    required this.primary,
    required this.onTap,
  });

  final _Candidate candidate;
  final bool primary;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final TextTheme textTheme = Theme.of(context).textTheme;
    return Semantics(
      button: true,
      label: 'Choisir le nombre ${candidate.number}, '
          'en zarma ${candidate.zarmaText}.',
      child: ExcludeSemantics(
        child: Card(
          margin: EdgeInsets.zero,
          child: InkWell(
            key: Key('candidate-option-${candidate.number}'),
            onTap: onTap,
            borderRadius: BorderRadius.circular(12),
            child: Padding(
              padding: const EdgeInsets.symmetric(
                horizontal: 20,
                vertical: 16,
              ),
              child: Row(
                children: <Widget>[
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: <Widget>[
                        Text(
                          candidate.number.toString(),
                          style: primary
                              ? textTheme.displaySmall
                              : textTheme.headlineSmall,
                        ),
                        const SizedBox(height: 4),
                        Text(
                          candidate.zarmaText,
                          style: textTheme.titleMedium,
                        ),
                      ],
                    ),
                  ),
                  const Icon(Icons.chevron_right),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _RepeatBody extends StatelessWidget {
  const _RepeatBody({
    required this.busy,
    required this.onRecordAgain,
    required this.error,
  });

  final bool busy;
  final VoidCallback? onRecordAgain;
  final Widget error;

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Semantics(
          liveRegion: true,
          label: 'Aucun nombre n’a pu être identifié avec assez de certitude. '
              'Réenregistrez en articulant un seul nombre.',
          child: ExcludeSemantics(
            child: Column(
              children: <Widget>[
                const Icon(Icons.hearing_disabled_outlined, size: 72),
                const SizedBox(height: 16),
                Text(
                  'Nous n’avons pas pu identifier de nombre avec assez de '
                  'certitude.',
                  key: const Key('repeat-message'),
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                const SizedBox(height: 8),
                const Text(
                  'Réenregistrez en articulant un seul nombre.',
                  textAlign: TextAlign.center,
                ),
              ],
            ),
          ),
        ),
        if (busy) ...<Widget>[
          const SizedBox(height: 24),
          const LinearProgressIndicator(
            key: Key('feedback-progress-indicator'),
          ),
        ],
        const SizedBox(height: 32),
        FilledButton.icon(
          key: const Key('record-again-button'),
          onPressed: onRecordAgain,
          icon: const Icon(Icons.mic),
          label: const Text('Réenregistrer'),
        ),
        error,
      ],
    );
  }
}
