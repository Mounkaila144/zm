import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:zarma_mobile/feedback/feedback_controller.dart';
import 'package:zarma_mobile/feedback/feedback_models.dart';
import 'package:zarma_mobile/feedback/feedback_repository.dart';
import 'package:zarma_mobile/models/recognition_result.dart';

class FakeFeedbackRepository implements FeedbackRepository {
  FakeFeedbackRepository(this.handler);

  final Future<FeedbackResponse> Function(
    FeedbackRequest request,
    CancelToken token,
  ) handler;

  int calls = 0;
  FeedbackRequest? lastRequest;
  String? lastModelVersion;
  String? lastGrammarVersion;

  @override
  Future<FeedbackResponse> submit({
    required FeedbackRequest request,
    required String expectedModelVersion,
    required String expectedGrammarVersion,
    required CancelToken cancelToken,
  }) {
    calls++;
    lastRequest = request;
    lastModelVersion = expectedModelVersion;
    lastGrammarVersion = expectedGrammarVersion;
    return handler(request, cancelToken);
  }
}

void main() {
  test('construit la requête avec anon_id et hérite des versions', () async {
    final FakeFeedbackRepository repository =
        FakeFeedbackRepository((_, __) async => _receipt(proposedNumber: 42));
    final FeedbackController controller = _controller(repository);

    final FeedbackResponse? response = await controller.submit(
      recognition: _recognition(),
      feedbackType: FeedbackType.confirmed,
      proposedNumber: 42,
    );

    expect(response, isNotNull);
    expect(controller.state.status, FeedbackStatus.success);
    expect(repository.lastRequest?.anonId, 'anon-id');
    expect(repository.lastRequest?.recognitionId, 'rec-id');
    expect(repository.lastRequest?.feedbackType, FeedbackType.confirmed);
    expect(repository.lastRequest?.proposedNumber, 42);
    expect(repository.lastRequest?.correctedNumber, isNull);
    expect(repository.lastModelVersion, 'mock');
    expect(repository.lastGrammarVersion, 'v1');
    controller.dispose();
  });

  test('un double tap ne déclenche qu’un seul envoi', () async {
    final Completer<FeedbackResponse> pending = Completer<FeedbackResponse>();
    final FakeFeedbackRepository repository =
        FakeFeedbackRepository((_, __) => pending.future);
    final FeedbackController controller = _controller(repository);

    final Future<FeedbackResponse?> first = controller.submit(
      recognition: _recognition(),
      feedbackType: FeedbackType.confirmed,
      proposedNumber: 42,
    );
    final FeedbackResponse? second = await controller.submit(
      recognition: _recognition(),
      feedbackType: FeedbackType.confirmed,
      proposedNumber: 42,
    );

    expect(second, isNull);
    expect(controller.state.status, FeedbackStatus.submitting);
    expect(repository.calls, 1);

    pending.complete(_receipt(proposedNumber: 42));
    expect(await first, isNotNull);
    expect(controller.state.status, FeedbackStatus.success);
    controller.dispose();
  });

  test('un échec passe en erreur puis un retry utilisateur renvoie', () async {
    int calls = 0;
    final FakeFeedbackRepository repository = FakeFeedbackRepository((_, __) {
      calls++;
      if (calls == 1) {
        throw const FeedbackFailure(
          type: FeedbackFailureType.serviceUnavailable,
          message: 'Le service est momentanément indisponible.',
        );
      }
      return Future<FeedbackResponse>.value(_receipt(proposedNumber: 42));
    });
    final FeedbackController controller = _controller(repository);

    final FeedbackResponse? failed = await controller.submit(
      recognition: _recognition(),
      feedbackType: FeedbackType.confirmed,
      proposedNumber: 42,
    );
    expect(failed, isNull);
    expect(controller.state.status, FeedbackStatus.error);
    expect(controller.state.failure?.type,
        FeedbackFailureType.serviceUnavailable);

    final FeedbackResponse? retried = await controller.submit(
      recognition: _recognition(),
      feedbackType: FeedbackType.confirmed,
      proposedNumber: 42,
    );
    expect(retried, isNotNull);
    expect(controller.state.status, FeedbackStatus.success);
    expect(repository.calls, 2);
    controller.dispose();
  });

  test('une annulation volontaire ne produit pas d’erreur technique', () async {
    final FakeFeedbackRepository repository = FakeFeedbackRepository(
      (_, __) async => throw const FeedbackFailure(
        type: FeedbackFailureType.cancelled,
        message: '',
      ),
    );
    final FeedbackController controller = _controller(repository);

    final FeedbackResponse? response = await controller.submit(
      recognition: _recognition(),
      feedbackType: FeedbackType.repeatRequested,
      proposedNumber: null,
    );

    expect(response, isNull);
    expect(controller.state.status, FeedbackStatus.idle);
    expect(controller.state.failure, isNull);
    controller.dispose();
  });

  test('dispose annule la requête en vol', () async {
    final Completer<void> cancelled = Completer<void>();
    final FakeFeedbackRepository repository = FakeFeedbackRepository((
      FeedbackRequest request,
      CancelToken token,
    ) {
      final Completer<FeedbackResponse> completer =
          Completer<FeedbackResponse>();
      token.whenCancel.then((_) {
        cancelled.complete();
        completer.completeError(
          const FeedbackFailure(
            type: FeedbackFailureType.cancelled,
            message: '',
          ),
        );
      });
      return completer.future;
    });
    final FeedbackController controller = _controller(repository);

    unawaited(
      controller.submit(
        recognition: _recognition(),
        feedbackType: FeedbackType.confirmed,
        proposedNumber: 42,
      ),
    );
    controller.dispose();

    await cancelled.future;
    expect(cancelled.isCompleted, isTrue);
  });
}

FeedbackController _controller(FeedbackRepository repository) {
  return FeedbackController(
    repository: repository,
    anonId: 'anon-id',
    cancelTokenFactory: CancelToken.new,
  );
}

RecognitionResult _recognition() {
  return const RecognitionResult(
    id: 'rec-id',
    recognizedNumber: 42,
    zarmaText: 'waranka cindi hinka',
    normalizedText: 'waranka cindi hinka',
    confidence: 0.6,
    decision: Decision.confirm,
    modelVersion: 'mock',
    grammarVersion: 'v1',
  );
}

FeedbackResponse _receipt({required int? proposedNumber}) {
  return FeedbackResponse(
    id: 'feedback-id',
    recognitionId: 'rec-id',
    anonId: 'anon-id',
    feedbackType: FeedbackType.confirmed,
    proposedNumber: proposedNumber,
    correctedNumber: null,
    modelVersion: 'mock',
    grammarVersion: 'v1',
    createdAt: DateTime.utc(2026, 7, 24),
  );
}
