import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zarma_mobile/config/anon_id.dart';
import 'package:zarma_mobile/feedback/feedback_models.dart';
import 'package:zarma_mobile/feedback/feedback_repository.dart';
import 'package:zarma_mobile/models/recognition_result.dart';
import 'package:zarma_mobile/recognition/recognition_controller.dart';

enum FeedbackStatus { idle, submitting, success, error }

class FeedbackState {
  const FeedbackState({
    this.status = FeedbackStatus.idle,
    this.response,
    this.failure,
  });

  final FeedbackStatus status;
  final FeedbackResponse? response;
  final FeedbackFailure? failure;

  bool get isBusy => status == FeedbackStatus.submitting;
}

/// Orchestre l'envoi d'un feedback : sérialise les actions, verrouille pendant
/// l'envoi (anti double tap) et n'expose que des états UI sûrs. Aucun retry
/// automatique : l'API feedback n'est pas idempotente.
class FeedbackController extends StateNotifier<FeedbackState> {
  FeedbackController({
    required this._repository,
    required this._anonId,
    required this._cancelTokenFactory,
  })  : super(const FeedbackState());

  final FeedbackRepository _repository;
  final String _anonId;
  final CancelTokenFactory _cancelTokenFactory;
  CancelToken? _cancelToken;

  /// Envoie un feedback pour `recognition`. Retourne le receipt validé en cas
  /// de succès, `null` sinon (occupé, annulé, échec ou écran détruit). La
  /// navigation ne doit se faire que sur un retour non nul.
  Future<FeedbackResponse?> submit({
    required RecognitionResult recognition,
    required FeedbackType feedbackType,
    required int? proposedNumber,
    int? correctedNumber,
  }) async {
    if (state.status == FeedbackStatus.submitting) {
      return null;
    }
    final FeedbackRequest request = FeedbackRequest(
      recognitionId: recognition.id,
      anonId: _anonId,
      feedbackType: feedbackType,
      proposedNumber: proposedNumber,
      correctedNumber: correctedNumber,
    );

    _cancelToken = _cancelTokenFactory();
    state = const FeedbackState(status: FeedbackStatus.submitting);
    try {
      final FeedbackResponse response = await _repository.submit(
        request: request,
        expectedModelVersion: recognition.modelVersion,
        expectedGrammarVersion: recognition.grammarVersion,
        cancelToken: _cancelToken!,
      );
      if (!mounted) {
        return null;
      }
      state = FeedbackState(
        status: FeedbackStatus.success,
        response: response,
      );
      return response;
    } on FeedbackFailure catch (failure) {
      if (!mounted) {
        return null;
      }
      if (failure.isCancelled) {
        // Annulation volontaire (dispose) : jamais de message technique.
        state = const FeedbackState();
        return null;
      }
      state = FeedbackState(
        status: FeedbackStatus.error,
        failure: failure,
      );
      return null;
    }
  }

  @override
  void dispose() {
    _cancelToken?.cancel('screen_disposed');
    super.dispose();
  }
}

final feedbackControllerProvider =
    StateNotifierProvider.autoDispose<FeedbackController, FeedbackState>((ref) {
  return FeedbackController(
    repository: ref.watch(feedbackRepositoryProvider),
    anonId: ref.watch(anonIdProvider),
    cancelTokenFactory: ref.watch(cancelTokenFactoryProvider),
  );
});
