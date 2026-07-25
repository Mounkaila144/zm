import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:zarma_mobile/features/contribution/application/consent_controller.dart';
import 'package:zarma_mobile/features/contribution/application/contribution_controller.dart';
import 'package:zarma_mobile/features/contribution/data/consent_repository.dart';
import 'package:zarma_mobile/features/contribution/data/contribution_metadata_source.dart';
import 'package:zarma_mobile/features/contribution/data/contribution_prompt_repository.dart';
import 'package:zarma_mobile/features/contribution/data/contribution_upload_repository.dart';
import 'package:zarma_mobile/features/contribution/data/contribution_withdrawal_repository.dart';
import 'package:zarma_mobile/features/contribution/models/contribution_models.dart';
import 'package:zarma_mobile/features/contribution/presentation/contribution_route.dart';
import 'package:zarma_mobile/recording/audio_recording_models.dart';
import 'package:zarma_mobile/recording/audio_recording_service.dart';
import 'package:zarma_mobile/recording/microphone_permission.dart';
import 'package:zarma_mobile/recording/recording_controller.dart';
import 'package:zarma_mobile/recording/recording_ticker.dart';

class _UnusedConsentRepository implements ConsentRepository {
  @override
  Future<ConsentAcceptance> accept({
    required String anonId,
    required String consentVersion,
    required CancelToken cancelToken,
  }) {
    throw UnimplementedError();
  }

  @override
  Future<ConsentContent> fetchCurrent({required CancelToken cancelToken}) {
    throw UnimplementedError();
  }
}

class _FixedConsentController extends ConsentController {
  _FixedConsentController(ConsentState initial)
      : super(
          repository: _UnusedConsentRepository(),
          anonId: '00000000-0000-4000-8000-000000000042',
          cancelTokenFactory: CancelToken.new,
          loadOnCreate: false,
        ) {
    state = initial;
  }
}

class _UnusedPromptRepository implements ContributionPromptRepository {
  @override
  Future<ContributionPrompt> nextPrompt({
    required CancelToken cancelToken,
  }) {
    throw UnimplementedError();
  }
}

class _UnusedMetadataSource implements ContributionMetadataSource {
  @override
  Future<ContributionMetadata> load() {
    throw UnimplementedError();
  }
}

class _UnusedUploadRepository implements ContributionUploadRepository {
  @override
  Future<ContributionReceipt> upload({
    required PendingContribution contribution,
    required CancelToken cancelToken,
  }) {
    throw UnimplementedError();
  }
}

class _UnusedWithdrawalRepository implements ContributionWithdrawalRepository {
  @override
  Future<void> withdraw({
    required String anonId,
    required CancelToken cancelToken,
  }) {
    throw UnimplementedError();
  }
}

class _UnusedAudioService implements AudioRecordingService {
  @override
  Stream<double> amplitudeLevels() => const Stream<double>.empty();

  @override
  Future<void> cancel() async {}

  @override
  Future<void> deleteTemporary(String? path) async {}

  @override
  Future<void> dispose() async {}

  @override
  Future<AudioFileInspection> inspect(String path) {
    throw UnimplementedError();
  }

  @override
  Future<String> start() {
    throw UnimplementedError();
  }

  @override
  Future<String?> stop() {
    throw UnimplementedError();
  }
}

class _UnusedPermission implements MicrophonePermissionGateway {
  @override
  Future<MicrophonePermissionStatus> check() {
    throw UnimplementedError();
  }

  @override
  Future<bool> openSettings() async => true;

  @override
  Future<MicrophonePermissionStatus> request() {
    throw UnimplementedError();
  }
}

class _UnusedTicker implements RecordingTicker {
  @override
  Stream<Duration> get ticks => const Stream<Duration>.empty();

  @override
  Future<void> dispose() async {}
}

class _WidgetContributionController extends ContributionController {
  _WidgetContributionController({
    required RecordingController recording,
    bool startWithError = false,
    void Function()? onWithdrawalCompleted,
  })  : _promptNumber = 100,
        _completeWithdrawal = onWithdrawalCompleted ?? _doNothing,
        super(
          promptRepository: _UnusedPromptRepository(),
          uploadRepository: _UnusedUploadRepository(),
          withdrawalRepository: _UnusedWithdrawalRepository(),
          metadataSource: _UnusedMetadataSource(),
          recordingController: recording,
          anonId: '00000000-0000-4000-8000-000000000042',
          consent: _validConsent(),
          onWithdrawalCompleted: onWithdrawalCompleted ?? _doNothing,
          cancelTokenFactory: CancelToken.new,
          loadOnCreate: false,
        ) {
    state = startWithError
        ? const ContributionState(
            phase: ContributionPhase.error,
            message: 'Impossible de charger un nombre à prononcer.',
          )
        : ContributionState(
            phase: ContributionPhase.promptReady,
            prompt: _prompt(100),
          );
  }

  int _promptNumber;
  final void Function() _completeWithdrawal;
  int loadCalls = 0;
  int cancelCalls = 0;

  static void _doNothing() {}

  static ContributionPrompt _prompt(int number) {
    return ContributionPrompt(
      expectedNumber: number,
      expectedPrompt: number == 100 ? 'zangou' : 'zangou hinka nda gou',
      category: ContributionPromptCategory.hundred,
      grammarVersion: '1.1.0',
    );
  }

  @override
  Future<void> loadNextPrompt() async {
    loadCalls++;
    _promptNumber++;
    state = ContributionState(
      phase: ContributionPhase.promptReady,
      prompt: _prompt(_promptNumber),
    );
  }

  @override
  Future<void> startRecording() async {
    state = ContributionState(
      phase: ContributionPhase.recording,
      prompt: state.prompt,
      recording: const RecordingState(phase: RecordingPhase.recording),
    );
  }

  @override
  Future<void> stopRecording() async {
    const AudioHandoff handoff = AudioHandoff(
      path: '/tmp/widget-contribution.wav',
      duration: Duration(seconds: 1),
      sizeBytes: 32044,
    );
    state = ContributionState(
      phase: ContributionPhase.audioReady,
      prompt: state.prompt,
      recording: const RecordingState(
        phase: RecordingPhase.ready,
        handoff: handoff,
      ),
      pending: PendingContribution(
        audio: handoff,
        expectedNumber: state.prompt!.expectedNumber,
        expectedPrompt: state.prompt!.expectedPrompt,
        anonId: '00000000-0000-4000-8000-000000000042',
        consentId: '11111111-1111-4111-8111-111111111111',
        grammarVersion: '1.1.0',
        consentVersion: '1.0.0',
      ),
    );
  }

  @override
  Future<void> restartRecording() => startRecording();

  @override
  Future<void> submitPending() async {
    state = ContributionState(
      phase: ContributionPhase.success,
      prompt: _prompt(101),
      recording: const RecordingState(),
      receipt: ContributionReceipt(
        id: '22222222-2222-4222-8222-222222222222',
        status: 'pending',
        expectedNumber: 100,
        expectedPrompt: 'zangou',
        modelVersion: 'mock-1',
        grammarVersion: '1.1.0',
        createdAt: DateTime.utc(2026, 7, 24),
      ),
      message: 'Contribution envoyée. Merci !',
    );
  }

  @override
  Future<void> continueAfterSuccess() async {
    state = ContributionState(
      phase: ContributionPhase.promptReady,
      prompt: state.prompt,
      recording: const RecordingState(),
    );
  }

  @override
  Future<void> confirmWithdrawal() async {
    state = ContributionState(
      phase: state.phase,
      prompt: state.prompt,
      recording: const RecordingState(),
      withdrawalPhase: ContributionWithdrawalPhase.success,
      withdrawalMessage: 'Vos contributions ont été retirées.',
    );
    _completeWithdrawal();
  }

  void showWithdrawalError() {
    state = ContributionState(
      phase: state.phase,
      prompt: state.prompt,
      recording: const RecordingState(),
      withdrawalPhase: ContributionWithdrawalPhase.error,
      withdrawalMessage: 'Le retrait est incomplet. Réessayez.',
    );
  }

  void showWithdrawalProgress() {
    state = ContributionState(
      phase: state.phase,
      prompt: state.prompt,
      recording: const RecordingState(),
      withdrawalPhase: ContributionWithdrawalPhase.withdrawing,
      withdrawalMessage: 'Suppression sécurisée…',
    );
  }

  @override
  Future<void> retryWithdrawal() => confirmWithdrawal();

  void showPermissionDenied() {
    state = ContributionState(
      phase: ContributionPhase.promptReady,
      prompt: state.prompt,
      recording: const RecordingState(
        phase: RecordingPhase.permissionDenied,
        message: 'Le micro est nécessaire.',
      ),
    );
  }

  void showSending() {
    state = ContributionState(
      phase: ContributionPhase.sending,
      prompt: state.prompt,
      recording: state.recording,
      message: 'Envoi sécurisé de la contribution…',
    );
  }

  void showUploadError() {
    state = ContributionState(
      phase: ContributionPhase.uploadError,
      prompt: state.prompt,
      recording: const RecordingState(),
      message: 'Trop d’envois. Patientez avant de recommencer.',
    );
  }

  @override
  Future<void> cancelFlow() async {
    cancelCalls++;
    state = const ContributionState();
  }
}

ConsentState _validConsent() {
  return ConsentState(
    phase: ConsentPhase.ready,
    content: const ConsentContent(
      consentVersion: '1.0.0',
      text: 'Consentement',
    ),
    acceptance: ConsentAcceptance(
      id: '11111111-1111-4111-8111-111111111111',
      anonId: '00000000-0000-4000-8000-000000000042',
      consentVersion: '1.0.0',
      acceptedAt: DateTime.utc(2026, 7, 24),
      withdrawn: false,
    ),
  );
}

RecordingController _recordingController() {
  return RecordingController(
    service: _UnusedAudioService(),
    permissionGateway: _UnusedPermission(),
    tickerFactory: _UnusedTicker.new,
  );
}

void main() {
  testWidgets('la garde conserve un consentement invalide sur ConsentScreen',
      (WidgetTester tester) async {
    final RecordingController recording = _recordingController();
    final _WidgetContributionController contribution =
        _WidgetContributionController(recording: recording);
    addTearDown(recording.dispose);

    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          consentStatusProvider.overrideWith(
            (ref) => _FixedConsentController(const ConsentState()),
          ),
          contributionControllerProvider.overrideWith((ref) => contribution),
        ],
        child: const MaterialApp(home: ContributionRoute()),
      ),
    );
    await tester.pump();

    expect(find.byKey(const Key('consent-screen')), findsOneWidget);
    expect(find.byKey(const Key('contribution-screen')), findsNothing);
    expect(contribution.loadCalls, 0);
  });

  testWidgets('affiche le prompt, enregistre, envoie puis continue',
      (WidgetTester tester) async {
    final RecordingController recording = _recordingController();
    final _WidgetContributionController contribution =
        _WidgetContributionController(recording: recording);
    addTearDown(recording.dispose);
    final SemanticsHandle semantics = tester.ensureSemantics();

    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          consentStatusProvider.overrideWith(
            (ref) => _FixedConsentController(_validConsent()),
          ),
          contributionControllerProvider.overrideWith((ref) => contribution),
        ],
        child: const MaterialApp(home: ContributionRoute()),
      ),
    );
    await tester.pump();

    expect(find.byKey(const Key('contribution-screen')), findsOneWidget);
    expect(find.text('100'), findsOneWidget);
    expect(find.text('zangou'), findsOneWidget);
    expect(
      find.bySemanticsLabel('Démarrer l’enregistrement consenti'),
      findsOneWidget,
    );

    await tester.tap(
      find.byKey(const Key('begin-contribution-recording-button')),
    );
    await tester.pump();
    expect(
      find.byKey(const Key('contribution-active-microphone')),
      findsOneWidget,
    );
    expect(find.text('zangou'), findsOneWidget);

    await tester
        .tap(find.byKey(const Key('stop-contribution-recording-button')));
    await tester.pump();
    expect(find.byKey(const Key('contribution-audio-ready')), findsOneWidget);
    expect(find.byKey(const Key('submit-contribution-button')), findsOneWidget);

    await tester.tap(find.byKey(const Key('submit-contribution-button')));
    await tester.pump();
    expect(
      find.byKey(const Key('contribution-upload-success')),
      findsOneWidget,
    );
    expect(find.text('Contribution envoyée. Merci !'), findsOneWidget);

    await tester.tap(
      find.byKey(const Key('continue-after-contribution-button')),
    );
    await tester.pump();
    expect(find.text('101'), findsOneWidget);
    semantics.dispose();
  });

  testWidgets('une erreur de prompt propose Réessayer puis récupère',
      (WidgetTester tester) async {
    final RecordingController recording = _recordingController();
    final _WidgetContributionController contribution =
        _WidgetContributionController(
      recording: recording,
      startWithError: true,
    );
    addTearDown(recording.dispose);

    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          consentStatusProvider.overrideWith(
            (ref) => _FixedConsentController(_validConsent()),
          ),
          contributionControllerProvider.overrideWith((ref) => contribution),
        ],
        child: const MaterialApp(home: ContributionRoute()),
      ),
    );
    await tester.pump();

    expect(
      find.byKey(const Key('contribution-prompt-error')),
      findsOneWidget,
    );
    await tester.tap(
      find.byKey(const Key('retry-contribution-prompt-button')),
    );
    await tester.pump();

    expect(find.text('101'), findsOneWidget);
    expect(contribution.loadCalls, 1);
  });

  testWidgets('un refus micro expose une action de nouvelle demande',
      (WidgetTester tester) async {
    final RecordingController recording = _recordingController();
    final _WidgetContributionController contribution =
        _WidgetContributionController(recording: recording);
    contribution.showPermissionDenied();
    addTearDown(recording.dispose);

    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          consentStatusProvider.overrideWith(
            (ref) => _FixedConsentController(_validConsent()),
          ),
          contributionControllerProvider.overrideWith((ref) => contribution),
        ],
        child: const MaterialApp(home: ContributionRoute()),
      ),
    );
    await tester.pump();

    expect(
      find.byKey(const Key('retry-contribution-permission-button')),
      findsOneWidget,
    );
    await tester.tap(
      find.byKey(const Key('retry-contribution-permission-button')),
    );
    await tester.pump();
    expect(
      find.byKey(const Key('contribution-active-microphone')),
      findsOneWidget,
    );
  });

  testWidgets('affiche la progression et une erreur d’envoi actionnable',
      (WidgetTester tester) async {
    final RecordingController recording = _recordingController();
    final _WidgetContributionController contribution =
        _WidgetContributionController(recording: recording);
    addTearDown(recording.dispose);

    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          consentStatusProvider.overrideWith(
            (ref) => _FixedConsentController(_validConsent()),
          ),
          contributionControllerProvider.overrideWith((ref) => contribution),
        ],
        child: const MaterialApp(home: ContributionRoute()),
      ),
    );
    await tester.pump();

    contribution.showSending();
    await tester.pump();
    expect(
      find.byKey(const Key('contribution-upload-sending')),
      findsOneWidget,
    );
    expect(find.byType(CircularProgressIndicator), findsOneWidget);

    contribution.showUploadError();
    await tester.pump();
    expect(
      find.byKey(const Key('contribution-upload-error')),
      findsOneWidget,
    );
    expect(find.textContaining('Trop d’envois'), findsOneWidget);

    await tester.tap(
      find.byKey(const Key('retry-contribution-after-upload-button')),
    );
    await tester.pump();
    expect(
      find.byKey(const Key('contribution-active-microphone')),
      findsOneWidget,
    );
  });

  testWidgets(
      'confirme le retrait irréversible puis revient au consentement avec succès',
      (WidgetTester tester) async {
    final RecordingController recording = _recordingController();
    final _FixedConsentController consent =
        _FixedConsentController(_validConsent());
    final _WidgetContributionController contribution =
        _WidgetContributionController(
      recording: recording,
      onWithdrawalCompleted: consent.clearAcceptanceAfterWithdrawal,
    );
    addTearDown(recording.dispose);
    final SemanticsHandle semantics = tester.ensureSemantics();

    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          consentStatusProvider.overrideWith((ref) => consent),
          contributionControllerProvider.overrideWith((ref) => contribution),
        ],
        child: const MaterialApp(home: ContributionRoute()),
      ),
    );
    await tester.pump();

    expect(
      find.bySemanticsLabel('Retirer définitivement mes contributions'),
      findsOneWidget,
    );
    await tester.tap(find.byKey(const Key('request-withdrawal-button')));
    await tester.pumpAndSettle();

    expect(
      find.byKey(const Key('withdrawal-confirmation-dialog')),
      findsOneWidget,
    );
    expect(find.textContaining('irréversible'), findsOneWidget);
    await tester.tap(find.byKey(const Key('cancel-withdrawal-button')));
    await tester.pumpAndSettle();
    expect(
      find.byKey(const Key('withdrawal-confirmation-dialog')),
      findsNothing,
    );
    expect(find.byKey(const Key('contribution-screen')), findsOneWidget);

    await tester.tap(find.byKey(const Key('request-withdrawal-button')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('confirm-withdrawal-button')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('consent-screen')), findsOneWidget);
    expect(
      find.byKey(const Key('withdrawal-completed-message')),
      findsOneWidget,
    );
    expect(
      find.textContaining('audios supprimés'),
      findsOneWidget,
    );
    semantics.dispose();
  });

  testWidgets('affiche progression et erreur de retrait réessayable',
      (WidgetTester tester) async {
    final RecordingController recording = _recordingController();
    final _WidgetContributionController contribution =
        _WidgetContributionController(recording: recording);
    addTearDown(recording.dispose);

    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          consentStatusProvider.overrideWith(
            (ref) => _FixedConsentController(_validConsent()),
          ),
          contributionControllerProvider.overrideWith((ref) => contribution),
        ],
        child: const MaterialApp(home: ContributionRoute()),
      ),
    );
    await tester.pump();

    contribution.showWithdrawalProgress();
    await tester.pump();
    expect(
      find.byKey(const Key('contribution-withdrawal-progress')),
      findsOneWidget,
    );
    expect(find.byType(CircularProgressIndicator), findsOneWidget);

    contribution.showWithdrawalError();
    await tester.pump();
    expect(
      find.byKey(const Key('contribution-withdrawal-error')),
      findsOneWidget,
    );
    expect(find.textContaining('incomplet'), findsOneWidget);
    await tester.tap(find.byKey(const Key('retry-withdrawal-button')));
    await tester.pump();
    expect(
      find.byKey(const Key('contribution-withdrawal-success')),
      findsOneWidget,
    );
  });

  testWidgets('Annuler pendant la capture déclenche le nettoyage',
      (WidgetTester tester) async {
    final RecordingController recording = _recordingController();
    final _WidgetContributionController contribution =
        _WidgetContributionController(recording: recording);
    addTearDown(recording.dispose);

    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          consentStatusProvider.overrideWith(
            (ref) => _FixedConsentController(_validConsent()),
          ),
          contributionControllerProvider.overrideWith((ref) => contribution),
        ],
        child: const MaterialApp(home: ContributionRoute()),
      ),
    );
    await tester.pump();
    await tester.tap(
      find.byKey(const Key('begin-contribution-recording-button')),
    );
    await tester.pump();

    await tester.tap(find.byKey(const Key('cancel-contribution-button')));
    await tester.pump();

    expect(contribution.cancelCalls, 1);
  });
}
