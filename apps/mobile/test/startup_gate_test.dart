import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:zarma_mobile/features/contribution/application/consent_controller.dart';
import 'package:zarma_mobile/features/contribution/data/consent_repository.dart';
import 'package:zarma_mobile/screens/startup_gate.dart';
import 'package:zarma_mobile/update/mobile_update.dart';

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

ConsentController _consentController({required bool accepted}) {
  const String anonId = '00000000-0000-4000-8000-000000000001';
  return ConsentController(
    repository: _UnusedConsentRepository(),
    anonId: anonId,
    cancelTokenFactory: CancelToken.new,
    loadOnCreate: false,
    initialState: ConsentState(
      phase: ConsentPhase.ready,
      content: const ConsentContent(
        consentVersion: '2.0.0',
        text: 'Votre voix sera conservée pour entraîner les prochains modèles.',
      ),
      acceptance: accepted
          ? ConsentAcceptance(
              id: '11111111-1111-4111-8111-111111111111',
              anonId: anonId,
              consentVersion: '2.0.0',
              acceptedAt: DateTime(2026),
              withdrawn: false,
            )
          : null,
    ),
  );
}

Widget _app({
  required MobileUpdatePolicy policy,
  required bool accepted,
}) {
  return ProviderScope(
    overrides: <Override>[
      mobileUpdatePolicyProvider.overrideWith((ref) async => policy),
      consentStatusProvider.overrideWith(
        (ref) => _consentController(accepted: accepted),
      ),
    ],
    child: const MaterialApp(home: StartupGate()),
  );
}

void main() {
  testWidgets('une politique serveur indisponible bloque l’application', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          mobileUpdatePolicyProvider.overrideWith(
            (ref) => Future<MobileUpdatePolicy>.error(
              StateError('configuration absente'),
            ),
          ),
          consentStatusProvider.overrideWith(
            (ref) => _consentController(accepted: true),
          ),
        ],
        child: const MaterialApp(home: StartupGate()),
      ),
    );
    await tester.pump();

    expect(find.byKey(const Key('retry-startup-button')), findsOneWidget);
    expect(find.byKey(const Key('home-screen')), findsNothing);
    expect(find.byKey(const Key('consent-screen')), findsNothing);
  });

  testWidgets('un build ancien ne peut pas accéder à l’application', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      _app(
        policy: const MobileUpdatePolicy(
          minimumSupportedBuild: 3,
          latestBuild: 3,
          playStoreUrl: 'https://play.google.com/store/apps/details?id=test',
        ),
        accepted: true,
      ),
    );
    await tester.pump();

    expect(find.byKey(const Key('update-required-screen')), findsOneWidget);
    expect(find.byKey(const Key('mandatory-update-button')), findsOneWidget);
    expect(find.byKey(const Key('home-screen')), findsNothing);
  });

  testWidgets('sans accord, seul le consentement obligatoire est accessible', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      _app(
        policy: const MobileUpdatePolicy(
          minimumSupportedBuild: 1,
          latestBuild: 2,
          playStoreUrl: 'https://play.google.com/store/apps/details?id=test',
        ),
        accepted: false,
      ),
    );
    await tester.pump();

    expect(find.byKey(const Key('consent-screen')), findsOneWidget);
    expect(find.byKey(const Key('accept-consent-button')), findsOneWidget);
    expect(find.byKey(const Key('refuse-consent-button')), findsOneWidget);
    expect(find.byKey(const Key('home-screen')), findsNothing);
  });

  testWidgets('build courant et accord valide ouvrent l’accueil', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      _app(
        policy: const MobileUpdatePolicy(
          minimumSupportedBuild: 1,
          latestBuild: 2,
          playStoreUrl: 'https://play.google.com/store/apps/details?id=test',
        ),
        accepted: true,
      ),
    );
    await tester.pump();

    expect(find.byKey(const Key('home-screen')), findsOneWidget);
  });
}
