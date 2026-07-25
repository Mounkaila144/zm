import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zarma_mobile/features/contribution/application/consent_controller.dart';
import 'package:zarma_mobile/features/contribution/presentation/consent_screen.dart';
import 'package:zarma_mobile/features/contribution/presentation/contribution_screen.dart';

Widget contributionGuard(WidgetRef ref, Widget child) {
  final ConsentState consent = ref.watch(consentStatusProvider);
  return consent.hasValidConsent ? child : const ConsentScreen();
}

class ContributionRoute extends ConsumerWidget {
  const ContributionRoute({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return contributionGuard(ref, const ContributionScreen());
  }
}
