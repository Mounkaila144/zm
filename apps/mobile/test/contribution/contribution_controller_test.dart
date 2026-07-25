import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:zarma_mobile/features/contribution/application/consent_controller.dart';
import 'package:zarma_mobile/features/contribution/application/contribution_controller.dart';
import 'package:zarma_mobile/features/contribution/data/consent_repository.dart';
import 'package:zarma_mobile/features/contribution/data/contribution_metadata_source.dart';
import 'package:zarma_mobile/features/contribution/data/contribution_prompt_repository.dart';
import 'package:zarma_mobile/features/contribution/data/contribution_upload_repository.dart';
import 'package:zarma_mobile/features/contribution/data/contribution_withdrawal_repository.dart';
import 'package:zarma_mobile/features/contribution/models/contribution_models.dart';
import 'package:zarma_mobile/recording/audio_recording_models.dart';
import 'package:zarma_mobile/recording/audio_recording_service.dart';
import 'package:zarma_mobile/recording/microphone_permission.dart';
import 'package:zarma_mobile/recording/recording_controller.dart';
import 'package:zarma_mobile/recording/recording_ticker.dart';

class _FakePromptRepository implements ContributionPromptRepository {
  int calls = 0;
  int number = 100;

  @override
  Future<ContributionPrompt> nextPrompt({
    required CancelToken cancelToken,
  }) async {
    calls++;
    final int current = number++;
    return ContributionPrompt(
      expectedNumber: current,
      expectedPrompt: 'zangou $current',
      category: ContributionPromptCategory.asrConfusion,
      grammarVersion: '1.1.0',
    );
  }
}

class _FixedMetadataSource implements ContributionMetadataSource {
  const _FixedMetadataSource(this.metadata);

  final ContributionMetadata metadata;

  @override
  Future<ContributionMetadata> load() async => metadata;
}

class _FakeUploadRepository implements ContributionUploadRepository {
  _FakeUploadRepository({this.handler});

  final Future<ContributionReceipt> Function(
    PendingContribution contribution,
    CancelToken cancelToken,
  )? handler;
  final List<PendingContribution> uploads = <PendingContribution>[];
  CancelToken? token;

  @override
  Future<ContributionReceipt> upload({
    required PendingContribution contribution,
    required CancelToken cancelToken,
  }) {
    uploads.add(contribution);
    token = cancelToken;
    return handler?.call(contribution, cancelToken) ??
        Future<ContributionReceipt>.value(_receipt(contribution));
  }
}

class _FakeWithdrawalRepository implements ContributionWithdrawalRepository {
  _FakeWithdrawalRepository({this.handler});

  final Future<void> Function(String anonId, CancelToken cancelToken)? handler;
  int calls = 0;
  String? anonId;
  CancelToken? token;

  @override
  Future<void> withdraw({
    required String anonId,
    required CancelToken cancelToken,
  }) async {
    calls++;
    this.anonId = anonId;
    token = cancelToken;
    await handler?.call(anonId, cancelToken);
  }
}

class _FakeAudioService implements AudioRecordingService {
  final List<String?> deleted = <String?>[];
  final StreamController<double> amplitudes =
      StreamController<double>.broadcast();
  int cancelCalls = 0;

  @override
  Stream<double> amplitudeLevels() => amplitudes.stream;

  @override
  Future<void> cancel() async {
    cancelCalls++;
  }

  @override
  Future<void> deleteTemporary(String? path) async {
    deleted.add(path);
  }

  @override
  Future<void> dispose() async {
    await amplitudes.close();
  }

  @override
  Future<AudioFileInspection> inspect(String path) async {
    return const AudioFileInspection(
      exists: true,
      sizeBytes: 32044,
      duration: Duration(seconds: 1),
      isFormatValid: true,
    );
  }

  @override
  Future<String> start() async => '/tmp/contribution.wav';

  @override
  Future<String?> stop() async => '/tmp/contribution.wav';
}

class _GrantedPermission implements MicrophonePermissionGateway {
  @override
  Future<MicrophonePermissionStatus> check() async {
    return MicrophonePermissionStatus.granted;
  }

  @override
  Future<bool> openSettings() async => true;

  @override
  Future<MicrophonePermissionStatus> request() async {
    return MicrophonePermissionStatus.granted;
  }
}

class _SilentTicker implements RecordingTicker {
  @override
  Stream<Duration> get ticks => const Stream<Duration>.empty();

  @override
  Future<void> dispose() async {}
}

const String _anonId = '00000000-0000-4000-8000-000000000042';

ConsentState _validConsent() {
  return ConsentState(
    phase: ConsentPhase.ready,
    content: const ConsentContent(
      consentVersion: '1.0.0',
      text: 'Consentement',
    ),
    acceptance: ConsentAcceptance(
      id: '11111111-1111-4111-8111-111111111111',
      anonId: _anonId,
      consentVersion: '1.0.0',
      acceptedAt: DateTime.utc(2026, 7, 24),
      withdrawn: false,
    ),
  );
}

void main() {
  late _FakePromptRepository promptRepository;
  late _FakeAudioService audioService;
  late _FakeUploadRepository uploadRepository;
  late _FakeWithdrawalRepository withdrawalRepository;
  late RecordingController recordingController;
  late ContributionController controller;
  late bool withdrawalCompleted;

  ContributionController createController({
    ConsentState? consent,
    ContributionMetadata metadata = const ContributionMetadata(),
    ContributionUploadRepository? uploader,
    ContributionWithdrawalRepository? withdrawer,
  }) {
    return ContributionController(
      promptRepository: promptRepository,
      uploadRepository: uploader ?? uploadRepository,
      withdrawalRepository: withdrawer ?? withdrawalRepository,
      metadataSource: _FixedMetadataSource(metadata),
      recordingController: recordingController,
      anonId: _anonId,
      consent: consent ?? _validConsent(),
      onWithdrawalCompleted: () => withdrawalCompleted = true,
      cancelTokenFactory: CancelToken.new,
      loadOnCreate: false,
    );
  }

  setUp(() {
    promptRepository = _FakePromptRepository();
    uploadRepository = _FakeUploadRepository();
    withdrawalRepository = _FakeWithdrawalRepository();
    withdrawalCompleted = false;
    audioService = _FakeAudioService();
    recordingController = RecordingController(
      service: audioService,
      permissionGateway: _GrantedPermission(),
      tickerFactory: _SilentTicker.new,
    );
    controller = createController();
  });

  tearDown(() async {
    controller.dispose();
    recordingController.dispose();
    await audioService.dispose();
  });

  test('exige un consentement valide avant prompt et capture', () async {
    controller.dispose();
    controller = createController(consent: const ConsentState());

    await controller.loadNextPrompt();
    await controller.startRecording();

    expect(promptRepository.calls, 0);
    expect(recordingController.state.phase, RecordingPhase.idle);
    expect(controller.state.phase, ContributionPhase.inactive);
  });

  test('charge le prompt avant la capture et assemble toutes les métadonnées',
      () async {
    controller.dispose();
    controller = createController(
      metadata: const ContributionMetadata(
        region: 'Tillabéri',
        deviceInfo: 'android',
      ),
    );

    await controller.loadNextPrompt();
    expect(controller.state.phase, ContributionPhase.promptReady);
    expect(controller.state.prompt?.expectedNumber, 100);

    await controller.startRecording();
    expect(controller.state.phase, ContributionPhase.recording);
    await controller.stopRecording();
    await pumpEventQueue();

    final PendingContribution pending = controller.state.pending!;
    expect(controller.state.phase, ContributionPhase.audioReady);
    expect(pending.audio.path, '/tmp/contribution.wav');
    expect(pending.expectedNumber, 100);
    expect(pending.expectedPrompt, 'zangou 100');
    expect(pending.anonId, _anonId);
    expect(pending.consentId, '11111111-1111-4111-8111-111111111111');
    expect(pending.grammarVersion, '1.1.0');
    expect(pending.consentVersion, '1.0.0');
    expect(pending.region, 'Tillabéri');
    expect(pending.deviceInfo, 'android');
  });

  test('les métadonnées optionnelles nulles ne bloquent pas le brouillon',
      () async {
    await controller.loadNextPrompt();
    await controller.startRecording();
    await controller.stopRecording();
    await pumpEventQueue();

    expect(controller.state.pending?.region, isNull);
    expect(controller.state.pending?.deviceInfo, isNull);
  });

  test('changement de prompt et perte de consentement nettoient le temporaire',
      () async {
    await controller.loadNextPrompt();
    await controller.startRecording();
    await controller.stopRecording();
    await pumpEventQueue();

    await controller.loadNextPrompt();
    expect(audioService.deleted, contains('/tmp/contribution.wav'));
    expect(controller.state.prompt?.expectedNumber, 101);

    await controller.startRecording();
    await controller.updateConsent(const ConsentState());
    expect(controller.state.phase, ContributionPhase.inactive);
    expect(audioService.cancelCalls, greaterThanOrEqualTo(1));
  });

  test('envoie le brouillon, nettoie le WAV et précharge le prompt suivant',
      () async {
    await controller.loadNextPrompt();
    await controller.startRecording();
    await controller.stopRecording();
    await pumpEventQueue();

    await controller.submitPending();

    expect(uploadRepository.uploads, hasLength(1));
    expect(uploadRepository.uploads.single.expectedNumber, 100);
    expect(controller.state.phase, ContributionPhase.success);
    expect(controller.state.receipt?.status, 'pending');
    expect(controller.state.prompt?.expectedNumber, 101);
    expect(recordingController.state.handoff, isNull);
    expect(audioService.deleted, contains('/tmp/contribution.wav'));

    await controller.continueAfterSuccess();
    expect(controller.state.phase, ContributionPhase.promptReady);
    expect(controller.state.prompt?.expectedNumber, 101);
  });

  test('une erreur d’envoi est actionnable et nettoie toujours le WAV',
      () async {
    controller.dispose();
    uploadRepository = _FakeUploadRepository(
      handler: (_, __) async => throw const ContributionUploadFailure(
        type: ContributionUploadFailureType.noConnection,
        message: 'Impossible de joindre le serveur.',
      ),
    );
    controller = createController();
    await controller.loadNextPrompt();
    await controller.startRecording();
    await controller.stopRecording();
    await pumpEventQueue();

    await controller.submitPending();

    expect(controller.state.phase, ContributionPhase.uploadError);
    expect(controller.state.message, contains('joindre'));
    expect(controller.state.pending, isNull);
    expect(audioService.deleted, contains('/tmp/contribution.wav'));

    await controller.restartRecording();
    expect(controller.state.phase, ContributionPhase.recording);
  });

  test('annule immédiatement une requête en cours puis nettoie le flux',
      () async {
    controller.dispose();
    uploadRepository = _FakeUploadRepository(
      handler: (_, CancelToken token) async {
        await token.whenCancel;
        throw const ContributionUploadFailure(
          type: ContributionUploadFailureType.cancelled,
          message: 'Envoi annulé.',
        );
      },
    );
    controller = createController();
    await controller.loadNextPrompt();
    await controller.startRecording();
    await controller.stopRecording();
    await pumpEventQueue();

    final Future<void> upload = controller.submitPending();
    await pumpEventQueue();
    expect(controller.state.phase, ContributionPhase.sending);

    await controller.cancelFlow();
    await upload;

    expect(uploadRepository.token?.isCancelled, isTrue);
    expect(controller.state.phase, ContributionPhase.inactive);
    expect(audioService.deleted, contains('/tmp/contribution.wav'));
  });

  test('exige une confirmation avant tout retrait', () async {
    controller.requestWithdrawal();

    expect(
      controller.state.withdrawalPhase,
      ContributionWithdrawalPhase.confirmation,
    );
    expect(withdrawalRepository.calls, 0);

    controller.dismissWithdrawal();
    expect(
      controller.state.withdrawalPhase,
      ContributionWithdrawalPhase.idle,
    );
    expect(withdrawalRepository.calls, 0);
  });

  test(
      'retire après confirmation, nettoie la capture et invalide le consentement',
      () async {
    await controller.loadNextPrompt();
    await controller.startRecording();
    await controller.stopRecording();
    await pumpEventQueue();
    expect(recordingController.state.handoff, isNotNull);

    controller.requestWithdrawal();
    await controller.confirmWithdrawal();

    expect(withdrawalRepository.calls, 1);
    expect(withdrawalRepository.anonId, _anonId);
    expect(recordingController.state.handoff, isNull);
    expect(audioService.deleted, contains('/tmp/contribution.wav'));
    expect(withdrawalCompleted, isTrue);
    expect(
      controller.state.withdrawalPhase,
      ContributionWithdrawalPhase.success,
    );
  });

  test('le retrait confirmé annule un upload en cours avant son appel',
      () async {
    controller.dispose();
    uploadRepository = _FakeUploadRepository(
      handler: (_, CancelToken token) async {
        await token.whenCancel;
        throw const ContributionUploadFailure(
          type: ContributionUploadFailureType.cancelled,
          message: 'Envoi annulé.',
        );
      },
    );
    controller = createController();
    await controller.loadNextPrompt();
    await controller.startRecording();
    await controller.stopRecording();
    await pumpEventQueue();

    final Future<void> activeUpload = controller.submitPending();
    await pumpEventQueue();
    controller.requestWithdrawal();
    final Future<void> activeWithdrawal = controller.confirmWithdrawal();
    await Future.wait(<Future<void>>[activeUpload, activeWithdrawal]);

    expect(uploadRepository.token?.isCancelled, isTrue);
    expect(withdrawalRepository.calls, 1);
    expect(withdrawalCompleted, isTrue);
  });

  test('une erreur de retrait est réessayable', () async {
    controller.dispose();
    int attempts = 0;
    withdrawalRepository = _FakeWithdrawalRepository(
      handler: (_, __) async {
        attempts++;
        if (attempts == 1) {
          throw const ContributionWithdrawalFailure(
            type: ContributionWithdrawalFailureType.incomplete,
            message: 'Le retrait est incomplet. Réessayez.',
          );
        }
      },
    );
    controller = createController();

    await controller.confirmWithdrawal();
    expect(
      controller.state.withdrawalPhase,
      ContributionWithdrawalPhase.error,
    );
    expect(controller.state.withdrawalMessage, contains('incomplet'));
    expect(withdrawalCompleted, isFalse);

    await controller.retryWithdrawal();
    expect(withdrawalRepository.calls, 2);
    expect(withdrawalCompleted, isTrue);
    expect(
      controller.state.withdrawalPhase,
      ContributionWithdrawalPhase.success,
    );
  });

  test('dispose annule une requête de retrait en cours', () async {
    final Completer<void> cancelled = Completer<void>();
    final _FakeWithdrawalRepository slowRepository = _FakeWithdrawalRepository(
      handler: (_, CancelToken token) async {
        await token.whenCancel;
        cancelled.complete();
        throw const ContributionWithdrawalFailure(
          type: ContributionWithdrawalFailureType.cancelled,
          message: 'Retrait annulé.',
        );
      },
    );
    final ContributionController disposable = createController(
      withdrawer: slowRepository,
    );

    unawaited(disposable.confirmWithdrawal());
    await pumpEventQueue();
    disposable.dispose();
    await cancelled.future;

    expect(slowRepository.token?.isCancelled, isTrue);
  });
}

ContributionReceipt _receipt(PendingContribution contribution) {
  return ContributionReceipt(
    id: '22222222-2222-4222-8222-222222222222',
    status: 'pending',
    expectedNumber: contribution.expectedNumber,
    expectedPrompt: contribution.expectedPrompt,
    modelVersion: 'mock-1.0.0',
    grammarVersion: contribution.grammarVersion,
    createdAt: DateTime.utc(2026, 7, 24),
  );
}
