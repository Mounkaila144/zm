import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zarma_mobile/config/anon_id.dart';
import 'package:zarma_mobile/features/contribution/data/consent_repository.dart';

enum ConsentPhase { idle, loading, ready, submitting, error }

class ConsentState {
  const ConsentState({
    this.phase = ConsentPhase.idle,
    this.content,
    this.acceptance,
    this.failure,
    this.withdrawalCompleted = false,
  });

  final ConsentPhase phase;
  final ConsentContent? content;
  final ConsentAcceptance? acceptance;
  final ConsentFailure? failure;
  final bool withdrawalCompleted;

  bool get hasValidConsent {
    final ConsentContent? current = content;
    final ConsentAcceptance? accepted = acceptance;
    return current != null &&
        accepted != null &&
        !accepted.withdrawn &&
        accepted.consentVersion == current.consentVersion;
  }

  bool get isBusy =>
      phase == ConsentPhase.loading || phase == ConsentPhase.submitting;
}

class ConsentController extends StateNotifier<ConsentState> {
  ConsentController({
    required this._repository,
    required this._anonId,
    required this._cancelTokenFactory,
    bool loadOnCreate = true,
    ConsentState? initialState,
  })  : super(initialState ?? const ConsentState()) {
    if (loadOnCreate) {
      unawaited(loadCurrent());
    }
  }

  final ConsentRepository _repository;
  final String _anonId;
  final CancelToken Function() _cancelTokenFactory;
  CancelToken? _cancelToken;

  Future<void> loadCurrent() async {
    if (state.isBusy) {
      return;
    }
    _cancelToken?.cancel('replaced');
    _cancelToken = _cancelTokenFactory();
    state = ConsentState(
      phase: ConsentPhase.loading,
      content: state.content,
      acceptance: state.acceptance,
    );
    try {
      final ConsentContent content = await _repository.fetchCurrent(
        cancelToken: _cancelToken!,
      );
      if (!mounted) {
        return;
      }
      state = ConsentState(
        phase: ConsentPhase.ready,
        content: content,
        acceptance: content.acceptance,
      );
    } on ConsentFailure catch (failure) {
      if (!mounted || failure.isCancelled) {
        return;
      }
      state = ConsentState(
        phase: ConsentPhase.error,
        content: state.content,
        acceptance: state.acceptance,
        failure: failure,
      );
    }
  }

  Future<bool> acceptCurrent() async {
    final ConsentContent? current = state.content;
    if (current == null || state.isBusy || state.hasValidConsent) {
      return false;
    }
    _cancelToken?.cancel('replaced');
    _cancelToken = _cancelTokenFactory();
    state = ConsentState(
      phase: ConsentPhase.submitting,
      content: current,
      acceptance: state.acceptance,
    );
    try {
      final ConsentAcceptance acceptance = await _repository.accept(
        anonId: _anonId,
        consentVersion: current.consentVersion,
        cancelToken: _cancelToken!,
      );
      if (!mounted) {
        return false;
      }
      state = ConsentState(
        phase: ConsentPhase.ready,
        content: current,
        acceptance: acceptance,
      );
      return state.hasValidConsent;
    } on ConsentFailure catch (failure) {
      if (!mounted || failure.isCancelled) {
        return false;
      }
      state = ConsentState(
        phase: ConsentPhase.error,
        content: current,
        acceptance: state.acceptance,
        failure: failure,
      );
      return false;
    }
  }

  void clearAcceptanceAfterWithdrawal() {
    state = ConsentState(
      phase: ConsentPhase.ready,
      content: state.content,
      withdrawalCompleted: true,
    );
  }

  @override
  void dispose() {
    _cancelToken?.cancel('controller_disposed');
    super.dispose();
  }
}

final consentStatusProvider =
    StateNotifierProvider<ConsentController, ConsentState>((ref) {
  return ConsentController(
    repository: ref.watch(consentRepositoryProvider),
    anonId: ref.watch(anonIdProvider),
    cancelTokenFactory: CancelToken.new,
  );
});
