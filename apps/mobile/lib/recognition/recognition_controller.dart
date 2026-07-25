import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zarma_mobile/config/anon_id.dart';
import 'package:zarma_mobile/models/recognition_result.dart';
import 'package:zarma_mobile/network/api_client.dart';
import 'package:zarma_mobile/recognition/recognition_repository.dart';
import 'package:zarma_mobile/recording/audio_recording_models.dart';
import 'package:zarma_mobile/recording/recording_controller.dart';

enum RecognitionPhase { initial, processing, success, error, cancelled }

class RecognitionState {
  const RecognitionState({
    this.phase = RecognitionPhase.initial,
    this.result,
    this.failure,
  });

  final RecognitionPhase phase;
  final RecognitionResult? result;
  final RecognitionFailure? failure;
}

typedef CancelTokenFactory = CancelToken Function();
typedef HandoffCleanup = Future<void> Function();

class RecognitionController extends StateNotifier<RecognitionState> {
  RecognitionController({
    required RecognitionRepository repository,
    required AudioHandoff handoff,
    required String anonId,
    required CancelTokenFactory cancelTokenFactory,
    required HandoffCleanup cleanup,
  })  : _repository = repository,
        _handoff = handoff,
        _anonId = anonId,
        _cancelTokenFactory = cancelTokenFactory,
        _cleanup = cleanup,
        super(const RecognitionState());

  final RecognitionRepository _repository;
  final AudioHandoff _handoff;
  final String _anonId;
  final CancelTokenFactory _cancelTokenFactory;
  final HandoffCleanup _cleanup;
  CancelToken? _cancelToken;
  Future<void>? _operation;
  Future<void>? _cleanupOperation;

  Future<void> start() {
    return _operation ??= _run();
  }

  Future<void> _run() async {
    _cancelToken = _cancelTokenFactory();
    state = const RecognitionState(phase: RecognitionPhase.processing);
    RecognitionResult? result;
    RecognitionFailure? failure;
    try {
      result = await _repository.recognize(
        handoff: _handoff,
        anonId: _anonId,
        cancelToken: _cancelToken!,
      );
    } on RecognitionFailure catch (error) {
      failure = error;
    } catch (_) {
      failure = const RecognitionFailure(
        type: RecognitionFailureType.unknown,
        message: 'Le service n’a pas pu traiter la demande.',
      );
    } finally {
      await _cleanupOnce();
    }

    if (!mounted) {
      return;
    }
    if (result != null) {
      state = RecognitionState(
        phase: RecognitionPhase.success,
        result: result,
      );
    } else if (failure?.isCancelled ?? false) {
      state = const RecognitionState(phase: RecognitionPhase.cancelled);
    } else {
      state = RecognitionState(
        phase: RecognitionPhase.error,
        failure: failure,
      );
    }
  }

  Future<void> cancel() async {
    if (state.phase != RecognitionPhase.processing) {
      return;
    }
    _cancelToken?.cancel('user_cancelled');
    await _operation;
  }

  Future<void> _cleanupOnce() {
    return _cleanupOperation ??= _safeCleanup();
  }

  Future<void> _safeCleanup() async {
    try {
      await _cleanup();
    } catch (_) {
      // Le nettoyage est obligatoire mais ne doit jamais masquer le résultat
      // ou l'échec réseau principal. Il reste idempotent côté Recording.
    }
  }

  @override
  void dispose() {
    _cancelToken?.cancel('screen_disposed');
    if (_operation == null) {
      unawaited(_cleanupOnce());
    }
    super.dispose();
  }
}

final cancelTokenFactoryProvider = Provider<CancelTokenFactory>((ref) {
  return createCancelToken;
});

final recognitionControllerProvider = StateNotifierProvider.autoDispose
    .family<RecognitionController, RecognitionState, AudioHandoff>(
        (ref, handoff) {
  return RecognitionController(
    repository: ref.watch(recognitionRepositoryProvider),
    handoff: handoff,
    anonId: ref.watch(anonIdProvider),
    cancelTokenFactory: ref.watch(cancelTokenFactoryProvider),
    cleanup: ref.read(recordingControllerProvider.notifier).deleteHandoff,
  );
});
