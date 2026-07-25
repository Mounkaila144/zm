import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:zarma_mobile/models/recognition_result.dart';
import 'package:zarma_mobile/recognition/recognition_controller.dart';
import 'package:zarma_mobile/recognition/recognition_repository.dart';
import 'package:zarma_mobile/recording/audio_recording_models.dart';

class FakeRecognitionRepository implements RecognitionRepository {
  FakeRecognitionRepository(this.handler);

  final Future<RecognitionResult> Function(CancelToken token) handler;
  int calls = 0;

  @override
  Future<RecognitionResult> recognize({
    required AudioHandoff handoff,
    required String anonId,
    required CancelToken cancelToken,
  }) {
    calls++;
    return handler(cancelToken);
  }
}

void main() {
  test('démarre une fois, attend le nettoyage puis publie le succès', () async {
    final Completer<RecognitionResult> response =
        Completer<RecognitionResult>();
    final Completer<void> cleanup = Completer<void>();
    final FakeRecognitionRepository repository =
        FakeRecognitionRepository((_) => response.future);
    int cleanupCalls = 0;
    final RecognitionController controller = _controller(
      repository,
      cleanup: () {
        cleanupCalls++;
        return cleanup.future;
      },
    );

    final Future<void> first = controller.start();
    final Future<void> second = controller.start();
    expect(controller.state.phase, RecognitionPhase.processing);
    expect(repository.calls, 1);
    response.complete(_result(Decision.accept));
    await pumpEventQueue();
    expect(controller.state.phase, RecognitionPhase.processing);

    cleanup.complete();
    await Future.wait(<Future<void>>[first, second]);
    expect(controller.state.phase, RecognitionPhase.success);
    expect(controller.state.result?.decision, Decision.accept);
    expect(cleanupCalls, 1);
    controller.dispose();
  });

  for (final Decision decision in Decision.values) {
    test('conserve le résultat serveur ${decision.name}', () async {
      int cleanupCalls = 0;
      final RecognitionController controller = _controller(
        FakeRecognitionRepository((_) async => _result(decision)),
        cleanup: () async => cleanupCalls++,
      );

      await controller.start();

      expect(controller.state.phase, RecognitionPhase.success);
      expect(controller.state.result?.decision, decision);
      expect(cleanupCalls, 1);
      controller.dispose();
    });
  }

  test('erreur et annulation nettoient exactement une fois', () async {
    int errorCleanup = 0;
    final RecognitionController failed = _controller(
      FakeRecognitionRepository(
        (_) async => throw const RecognitionFailure(
          type: RecognitionFailureType.timeout,
          message: 'Le traitement a pris trop de temps.',
        ),
      ),
      cleanup: () async => errorCleanup++,
    );
    await failed.start();
    expect(failed.state.phase, RecognitionPhase.error);
    expect(failed.state.failure?.type, RecognitionFailureType.timeout);
    expect(errorCleanup, 1);
    failed.dispose();

    int cancelCleanup = 0;
    final FakeRecognitionRepository pending = FakeRecognitionRepository((
      CancelToken token,
    ) {
      final Completer<RecognitionResult> completer =
          Completer<RecognitionResult>();
      token.whenCancel.then((_) {
        completer.completeError(
          const RecognitionFailure(
            type: RecognitionFailureType.cancelled,
            message: '',
          ),
        );
      });
      return completer.future;
    });
    final RecognitionController cancelled = _controller(
      pending,
      cleanup: () async => cancelCleanup++,
    );
    unawaited(cancelled.start());
    await cancelled.cancel();
    expect(cancelled.state.phase, RecognitionPhase.cancelled);
    expect(cancelCleanup, 1);
    cancelled.dispose();
  });

  for (final RecognitionFailureType type in <RecognitionFailureType>[
    RecognitionFailureType.noConnection,
    RecognitionFailureType.invalidAudio,
    RecognitionFailureType.rateLimited,
    RecognitionFailureType.serviceUnavailable,
  ]) {
    test('publie l’échec controller ${type.name} sans retry', () async {
      final FakeRecognitionRepository repository = FakeRecognitionRepository(
        (_) async => throw RecognitionFailure(
          type: type,
          message: 'Message sûr',
        ),
      );
      final RecognitionController controller = _controller(
        repository,
        cleanup: () async {},
      );

      await controller.start();

      expect(controller.state.phase, RecognitionPhase.error);
      expect(controller.state.failure?.type, type);
      expect(repository.calls, 1);
      controller.dispose();
    });
  }

  test('dispose annule la requête et laisse le finally nettoyer', () async {
    int cleanupCalls = 0;
    final Completer<void> cancelled = Completer<void>();
    final FakeRecognitionRepository repository = FakeRecognitionRepository((
      CancelToken token,
    ) {
      final Completer<RecognitionResult> completer =
          Completer<RecognitionResult>();
      token.whenCancel.then((_) {
        cancelled.complete();
        completer.completeError(
          const RecognitionFailure(
            type: RecognitionFailureType.cancelled,
            message: '',
          ),
        );
      });
      return completer.future;
    });
    final RecognitionController controller = _controller(
      repository,
      cleanup: () async => cleanupCalls++,
    );
    final Future<void> operation = controller.start();

    controller.dispose();
    await cancelled.future;
    await operation;

    expect(cleanupCalls, 1);
  });
}

RecognitionController _controller(
  RecognitionRepository repository, {
  required Future<void> Function() cleanup,
}) {
  return RecognitionController(
    repository: repository,
    handoff: const AudioHandoff(
      path: '/tmp/take.wav',
      duration: Duration(seconds: 2),
      sizeBytes: 64044,
    ),
    anonId: 'anon-id',
    cancelTokenFactory: CancelToken.new,
    cleanup: cleanup,
  );
}

RecognitionResult _result(Decision decision) {
  return RecognitionResult(
    id: 'id',
    recognizedNumber: decision == Decision.accept ? 42 : null,
    zarmaText: decision == Decision.accept ? 'waranka cindi hinka' : '',
    normalizedText: '',
    confidence: 0.9,
    decision: decision,
    modelVersion: 'mock',
    grammarVersion: 'v1',
  );
}
