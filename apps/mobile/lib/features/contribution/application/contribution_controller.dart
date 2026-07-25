import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zarma_mobile/config/anon_id.dart';
import 'package:zarma_mobile/features/contribution/application/consent_controller.dart';
import 'package:zarma_mobile/features/contribution/data/contribution_metadata_source.dart';
import 'package:zarma_mobile/features/contribution/data/contribution_prompt_repository.dart';
import 'package:zarma_mobile/features/contribution/data/contribution_upload_repository.dart';
import 'package:zarma_mobile/features/contribution/data/contribution_withdrawal_repository.dart';
import 'package:zarma_mobile/features/contribution/models/contribution_models.dart';
import 'package:zarma_mobile/recognition/recognition_controller.dart';
import 'package:zarma_mobile/recording/audio_recording_models.dart';
import 'package:zarma_mobile/recording/recording_controller.dart';

enum ContributionPhase {
  inactive,
  loadingPrompt,
  promptReady,
  recording,
  audioReady,
  sending,
  success,
  uploadError,
  error,
}

enum ContributionWithdrawalPhase {
  idle,
  confirmation,
  withdrawing,
  success,
  error,
}

class ContributionState {
  const ContributionState({
    this.phase = ContributionPhase.inactive,
    this.prompt,
    this.recording = const RecordingState(),
    this.pending,
    this.receipt,
    this.message,
    this.withdrawalPhase = ContributionWithdrawalPhase.idle,
    this.withdrawalMessage,
  });

  final ContributionPhase phase;
  final ContributionPrompt? prompt;
  final RecordingState recording;
  final PendingContribution? pending;
  final ContributionReceipt? receipt;
  final String? message;
  final ContributionWithdrawalPhase withdrawalPhase;
  final String? withdrawalMessage;
}

class ContributionController extends StateNotifier<ContributionState> {
  ContributionController({
    required ContributionPromptRepository promptRepository,
    required ContributionUploadRepository uploadRepository,
    required ContributionWithdrawalRepository withdrawalRepository,
    required ContributionMetadataSource metadataSource,
    required RecordingController recordingController,
    required String anonId,
    required ConsentState consent,
    required void Function() onWithdrawalCompleted,
    required CancelToken Function() cancelTokenFactory,
    bool loadOnCreate = true,
  })  : _promptRepository = promptRepository,
        _uploadRepository = uploadRepository,
        _withdrawalRepository = withdrawalRepository,
        _metadataSource = metadataSource,
        _recordingController = recordingController,
        _anonId = anonId,
        _consent = consent,
        _onWithdrawalCompleted = onWithdrawalCompleted,
        _cancelTokenFactory = cancelTokenFactory,
        super(const ContributionState()) {
    _removeRecordingListener = _recordingController.addListener(
      _onRecordingChanged,
      fireImmediately: true,
    );
    if (loadOnCreate && _consent.hasValidConsent) {
      unawaited(loadNextPrompt());
    }
  }

  final ContributionPromptRepository _promptRepository;
  final ContributionUploadRepository _uploadRepository;
  final ContributionWithdrawalRepository _withdrawalRepository;
  final ContributionMetadataSource _metadataSource;
  final RecordingController _recordingController;
  final String _anonId;
  final CancelToken Function() _cancelTokenFactory;
  final void Function() _onWithdrawalCompleted;
  late final void Function() _removeRecordingListener;
  ConsentState _consent;
  CancelToken? _promptCancelToken;
  CancelToken? _uploadCancelToken;
  CancelToken? _withdrawalCancelToken;
  Future<void> _operation = Future<void>.value();
  bool _assemblingPending = false;

  bool get _hasValidConsent => _consent.hasValidConsent;

  Future<void> loadNextPrompt() => _serialize(_loadNextPrompt);

  Future<void> startRecording() => _serialize(_startRecording);

  Future<void> stopRecording() => _recordingController.stop();

  Future<void> restartRecording() => _serialize(_restartRecording);

  Future<void> submitPending() => _serialize(_submitPending);

  Future<void> continueAfterSuccess() => _serialize(_continueAfterSuccess);

  void requestWithdrawal() {
    if (state.withdrawalPhase == ContributionWithdrawalPhase.withdrawing) {
      return;
    }
    state = _withWithdrawal(
      phase: ContributionWithdrawalPhase.confirmation,
    );
  }

  void dismissWithdrawal() {
    if (state.withdrawalPhase == ContributionWithdrawalPhase.confirmation) {
      state = _withWithdrawal(phase: ContributionWithdrawalPhase.idle);
    }
  }

  Future<void> confirmWithdrawal() {
    _promptCancelToken?.cancel('withdrawal_started');
    _uploadCancelToken?.cancel('withdrawal_started');
    return _serialize(_withdrawContributions);
  }

  Future<void> retryWithdrawal() => confirmWithdrawal();

  Future<void> cancelFlow() {
    _promptCancelToken?.cancel('contribution_cancelled');
    _uploadCancelToken?.cancel('contribution_cancelled');
    _withdrawalCancelToken?.cancel('contribution_cancelled');
    return _serialize(_cancelFlow);
  }

  Future<void> openSettings() => _recordingController.openSettings();

  Future<void> refreshPermission() => _recordingController.refreshPermission();

  Future<void> onAppResumed() => _recordingController.onAppResumed();

  Future<void> updateConsent(ConsentState consent) async {
    _consent = consent;
    if (!_hasValidConsent) {
      await cancelFlow();
    }
  }

  Future<void> _loadNextPrompt() async {
    if (!_hasValidConsent) {
      await _cancelFlow();
      return;
    }
    await _cleanupRecording();
    _promptCancelToken?.cancel('prompt_replaced');
    _promptCancelToken = _cancelTokenFactory();
    state = ContributionState(
      phase: ContributionPhase.loadingPrompt,
      recording: _recordingController.state,
    );
    try {
      final ContributionPrompt prompt = await _promptRepository.nextPrompt(
        cancelToken: _promptCancelToken!,
      );
      if (!mounted || !_hasValidConsent) {
        return;
      }
      state = ContributionState(
        phase: ContributionPhase.promptReady,
        prompt: prompt,
        recording: _recordingController.state,
      );
    } on ContributionPromptFailure catch (failure) {
      if (!mounted || failure.isCancelled) {
        return;
      }
      state = ContributionState(
        phase: ContributionPhase.error,
        recording: _recordingController.state,
        message: failure.message,
      );
    } catch (_) {
      if (!mounted) {
        return;
      }
      state = ContributionState(
        phase: ContributionPhase.error,
        recording: _recordingController.state,
        message: 'Impossible de proposer un nombre pour le moment.',
      );
    }
  }

  Future<void> _startRecording() async {
    if (!_hasValidConsent || state.prompt == null) {
      await _cancelFlow();
      return;
    }
    await _recordingController.start();
  }

  Future<void> _restartRecording() async {
    if (!_hasValidConsent || state.prompt == null) {
      await _cancelFlow();
      return;
    }
    await _recordingController.deleteHandoff();
    if (mounted) {
      state = ContributionState(
        phase: ContributionPhase.promptReady,
        prompt: state.prompt,
        recording: _recordingController.state,
      );
    }
    await _recordingController.start();
  }

  Future<void> _cancelFlow() async {
    _promptCancelToken?.cancel('contribution_cancelled');
    _uploadCancelToken?.cancel('contribution_cancelled');
    _withdrawalCancelToken?.cancel('contribution_cancelled');
    await _recordingController.cancel();
    if (mounted) {
      state = ContributionState(
        recording: _recordingController.state,
      );
    }
  }

  Future<void> _cleanupRecording() async {
    final RecordingState recording = _recordingController.state;
    if (recording.phase != RecordingPhase.idle || recording.handoff != null) {
      await _recordingController.cancel();
    }
  }

  void _onRecordingChanged(RecordingState recording) {
    if (!mounted || state.phase == ContributionPhase.inactive) {
      return;
    }
    if (state.phase == ContributionPhase.sending ||
        state.phase == ContributionPhase.success ||
        state.phase == ContributionPhase.uploadError ||
        state.withdrawalPhase != ContributionWithdrawalPhase.idle) {
      return;
    }
    final ContributionPrompt? prompt = state.prompt;
    if (prompt == null) {
      return;
    }
    switch (recording.phase) {
      case RecordingPhase.recording:
      case RecordingPhase.requestingPermission:
      case RecordingPhase.validating:
        state = ContributionState(
          phase: ContributionPhase.recording,
          prompt: prompt,
          recording: recording,
        );
      case RecordingPhase.ready:
        state = ContributionState(
          phase: ContributionPhase.recording,
          prompt: prompt,
          recording: recording,
        );
        unawaited(_assemblePending(recording.handoff));
      case RecordingPhase.idle:
      case RecordingPhase.permissionDenied:
      case RecordingPhase.permissionPermanentlyDenied:
      case RecordingPhase.invalid:
      case RecordingPhase.error:
        state = ContributionState(
          phase: ContributionPhase.promptReady,
          prompt: prompt,
          recording: recording,
          message: recording.message,
        );
    }
  }

  Future<void> _assemblePending(AudioHandoff? handoff) async {
    if (_assemblingPending || handoff == null || !_hasValidConsent) {
      return;
    }
    final ContributionPrompt? prompt = state.prompt;
    final acceptance = _consent.acceptance;
    if (prompt == null || acceptance == null) {
      return;
    }
    _assemblingPending = true;
    ContributionMetadata metadata = const ContributionMetadata();
    try {
      metadata = await _metadataSource.load();
    } catch (_) {
      // Les métadonnées sont optionnelles et ne bloquent jamais le brouillon.
    } finally {
      _assemblingPending = false;
    }
    if (!mounted ||
        !_hasValidConsent ||
        _recordingController.state.handoff?.path != handoff.path) {
      return;
    }
    state = ContributionState(
      phase: ContributionPhase.audioReady,
      prompt: prompt,
      recording: _recordingController.state,
      pending: PendingContribution(
        audio: handoff,
        expectedNumber: prompt.expectedNumber,
        expectedPrompt: prompt.expectedPrompt,
        anonId: _anonId,
        consentId: acceptance.id,
        grammarVersion: prompt.grammarVersion,
        consentVersion: acceptance.consentVersion,
        region: metadata.region,
        deviceInfo: metadata.deviceInfo,
      ),
    );
  }

  Future<void> _submitPending() async {
    final PendingContribution? pending = state.pending;
    final ContributionPrompt? submittedPrompt = state.prompt;
    if (!_hasValidConsent || pending == null || submittedPrompt == null) {
      return;
    }

    _uploadCancelToken?.cancel('upload_replaced');
    final CancelToken uploadToken = _cancelTokenFactory();
    _uploadCancelToken = uploadToken;
    state = ContributionState(
      phase: ContributionPhase.sending,
      prompt: submittedPrompt,
      recording: _recordingController.state,
      pending: pending,
      message: 'Envoi sécurisé de la contribution…',
    );

    ContributionReceipt? receipt;
    ContributionUploadFailure? failure;
    try {
      receipt = await _uploadRepository.upload(
        contribution: pending,
        cancelToken: uploadToken,
      );
    } on ContributionUploadFailure catch (error) {
      failure = error;
    } catch (_) {
      failure = const ContributionUploadFailure(
        type: ContributionUploadFailureType.unknown,
        message: 'La contribution n’a pas pu être envoyée.',
      );
    } finally {
      if (identical(_uploadCancelToken, uploadToken)) {
        _uploadCancelToken = null;
      }
      try {
        await _recordingController.deleteHandoff();
      } catch (_) {
        try {
          await _recordingController.cancel();
        } catch (_) {
          // L'erreur locale ne doit jamais masquer le reçu ou l'erreur réseau.
        }
      }
    }

    if (!mounted) {
      return;
    }
    if (failure != null) {
      state = ContributionState(
        phase: ContributionPhase.uploadError,
        prompt: submittedPrompt,
        recording: _recordingController.state,
        message: failure.message,
      );
      return;
    }

    state = ContributionState(
      phase: ContributionPhase.success,
      prompt: submittedPrompt,
      recording: _recordingController.state,
      receipt: receipt,
      message: 'Contribution envoyée. Merci !',
    );
    await _prefetchPromptAfterSuccess(receipt!);
  }

  Future<void> _prefetchPromptAfterSuccess(
    ContributionReceipt receipt,
  ) async {
    _promptCancelToken?.cancel('prompt_replaced');
    final CancelToken promptToken = _cancelTokenFactory();
    _promptCancelToken = promptToken;
    try {
      final ContributionPrompt prompt = await _promptRepository.nextPrompt(
        cancelToken: promptToken,
      );
      if (!mounted ||
          !_hasValidConsent ||
          state.phase != ContributionPhase.success) {
        return;
      }
      state = ContributionState(
        phase: ContributionPhase.success,
        prompt: prompt,
        recording: _recordingController.state,
        receipt: receipt,
        message: 'Contribution envoyée. Merci !',
      );
    } on ContributionPromptFailure catch (failure) {
      if (!mounted || failure.isCancelled) {
        return;
      }
      state = ContributionState(
        phase: ContributionPhase.success,
        recording: _recordingController.state,
        receipt: receipt,
        message: 'Contribution envoyée. Merci !',
      );
    } catch (_) {
      if (mounted && state.phase == ContributionPhase.success) {
        state = ContributionState(
          phase: ContributionPhase.success,
          recording: _recordingController.state,
          receipt: receipt,
          message: 'Contribution envoyée. Merci !',
        );
      }
    }
  }

  Future<void> _continueAfterSuccess() async {
    if (!_hasValidConsent) {
      await _cancelFlow();
      return;
    }
    final ContributionPrompt? prompt = state.prompt;
    if (state.phase == ContributionPhase.success && prompt != null) {
      state = ContributionState(
        phase: ContributionPhase.promptReady,
        prompt: prompt,
        recording: _recordingController.state,
      );
      return;
    }
    await _loadNextPrompt();
  }

  Future<void> _withdrawContributions() async {
    state = _withWithdrawal(
      phase: ContributionWithdrawalPhase.withdrawing,
      message: 'Suppression sécurisée de vos contributions…',
    );
    try {
      await _recordingController.cancel();
      final CancelToken token = _cancelTokenFactory();
      _withdrawalCancelToken = token;
      await _withdrawalRepository.withdraw(
        anonId: _anonId,
        cancelToken: token,
      );
      if (!mounted) {
        return;
      }
      state = _withWithdrawal(
        phase: ContributionWithdrawalPhase.success,
        message: 'Vos contributions ont été retirées.',
      );
      _onWithdrawalCompleted();
    } on ContributionWithdrawalFailure catch (failure) {
      if (!mounted) {
        return;
      }
      state = _withWithdrawal(
        phase: ContributionWithdrawalPhase.error,
        message: failure.message,
      );
    } catch (_) {
      if (!mounted) {
        return;
      }
      state = _withWithdrawal(
        phase: ContributionWithdrawalPhase.error,
        message: 'Le retrait n’a pas pu être terminé. Réessayez.',
      );
    } finally {
      _withdrawalCancelToken = null;
    }
  }

  ContributionState _withWithdrawal({
    required ContributionWithdrawalPhase phase,
    String? message,
  }) {
    return ContributionState(
      phase: state.phase,
      prompt: state.prompt,
      recording: _recordingController.state,
      pending: state.pending,
      receipt: state.receipt,
      message: state.message,
      withdrawalPhase: phase,
      withdrawalMessage: message,
    );
  }

  Future<void> _serialize(Future<void> Function() action) {
    final Future<void> next = _operation.then<void>((_) => action());
    _operation = next.then<void>(
      (_) {},
      onError: (_, __) {},
    );
    return next;
  }

  @override
  void dispose() {
    _promptCancelToken?.cancel('contribution_disposed');
    _uploadCancelToken?.cancel('contribution_disposed');
    _withdrawalCancelToken?.cancel('contribution_disposed');
    _removeRecordingListener();
    unawaited(_recordingController.cancel());
    super.dispose();
  }
}

final contributionControllerProvider = StateNotifierProvider.autoDispose<
    ContributionController, ContributionState>((ref) {
  final ContributionController controller = ContributionController(
    promptRepository: ref.watch(contributionPromptRepositoryProvider),
    uploadRepository: ref.watch(contributionUploadRepositoryProvider),
    withdrawalRepository: ref.watch(contributionWithdrawalRepositoryProvider),
    metadataSource: ref.watch(contributionMetadataSourceProvider),
    recordingController: ref.watch(recordingControllerProvider.notifier),
    anonId: ref.watch(anonIdProvider),
    consent: ref.read(consentStatusProvider),
    onWithdrawalCompleted:
        ref.read(consentStatusProvider.notifier).clearAcceptanceAfterWithdrawal,
    cancelTokenFactory: ref.watch(cancelTokenFactoryProvider),
  );
  ref.listen<ConsentState>(consentStatusProvider, (_, ConsentState next) {
    unawaited(controller.updateConsent(next));
  });
  return controller;
});
