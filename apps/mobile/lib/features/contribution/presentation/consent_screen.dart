import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zarma_mobile/features/contribution/application/consent_controller.dart';
import 'package:zarma_mobile/widgets/brand_app_bar.dart';
import 'package:zarma_mobile/widgets/brand_footer.dart';

class ConsentScreen extends ConsumerWidget {
  const ConsentScreen({super.key, this.mandatory = false});

  final bool mandatory;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final ConsentState consent = ref.watch(consentStatusProvider);
    final bool hasText = consent.content != null;

    return Scaffold(
      key: const Key('consent-screen'),
      appBar: BrandAppBar(
        title: 'Votre accord',
        automaticallyImplyLeading: !mandatory,
      ),
      bottomNavigationBar: const BrandFooter(),
      body: SafeArea(
        child: hasText
            ? _ConsentBody(consent: consent, mandatory: mandatory)
            : _ConsentLoadingOrError(consent: consent),
      ),
    );
  }
}

class _ConsentLoadingOrError extends ConsumerWidget {
  const _ConsentLoadingOrError({required this.consent});

  final ConsentState consent;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (consent.phase == ConsentPhase.error) {
      return Center(
        key: const Key('consent-load-error'),
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Text(
                consent.failure?.message ??
                    'Le texte de consentement est indisponible.',
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 16),
              FilledButton.icon(
                key: const Key('consent-load-retry'),
                onPressed: () =>
                    ref.read(consentStatusProvider.notifier).loadCurrent(),
                icon: const Icon(Icons.refresh),
                label: const Text('Réessayer'),
              ),
            ],
          ),
        ),
      );
    }
    return const Center(
      child: CircularProgressIndicator(key: Key('consent-loading')),
    );
  }
}

class _ConsentBody extends ConsumerWidget {
  const _ConsentBody({
    required this.consent,
    required this.mandatory,
  });

  final ConsentState consent;
  final bool mandatory;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final bool submitting = consent.phase == ConsentPhase.submitting;
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 16, 24, 24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Text(
            'Votre voix aide ZarmaIA',
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.titleLarge,
          ),
          const SizedBox(height: 4),
          Text(
            'Version ${consent.content!.consentVersion}',
            key: const Key('consent-version'),
            style: Theme.of(context).textTheme.labelLarge,
          ),
          const SizedBox(height: 16),
          Expanded(
            child: SingleChildScrollView(
              key: const Key('consent-text-scroll'),
              child: SelectableText(
                consent.content!.text,
                key: const Key('consent-text'),
              ),
            ),
          ),
          if (consent.withdrawalCompleted) ...<Widget>[
            const SizedBox(height: 12),
            Semantics(
              liveRegion: true,
              child: const Text(
                'Vos contributions ont été retirées et leurs audios supprimés.',
                key: Key('withdrawal-completed-message'),
                textAlign: TextAlign.center,
              ),
            ),
          ],
          if (consent.phase == ConsentPhase.error) ...<Widget>[
            const SizedBox(height: 12),
            Semantics(
              liveRegion: true,
              child: Text(
                consent.failure?.message ??
                    'Le consentement n’a pas pu être confirmé.',
                key: const Key('consent-submit-error'),
                textAlign: TextAlign.center,
              ),
            ),
          ],
          const SizedBox(height: 16),
          SizedBox(
            height: 68,
            child: FilledButton.icon(
              key: const Key('accept-consent-button'),
              onPressed: submitting
                  ? null
                  : () =>
                      ref.read(consentStatusProvider.notifier).acceptCurrent(),
              icon: submitting
                  ? const SizedBox.square(
                      dimension: 24,
                      child: CircularProgressIndicator(
                        key: Key('consent-submit-progress'),
                        strokeWidth: 2,
                      ),
                    )
                  : const Icon(Icons.check_circle, size: 36),
              label: const Text('J’accepte'),
            ),
          ),
          if (mandatory) ...<Widget>[
            const SizedBox(height: 12),
            SizedBox(
              height: 60,
              child: OutlinedButton.icon(
                key: const Key('refuse-consent-button'),
                onPressed: submitting ? null : SystemNavigator.pop,
                icon: const Icon(Icons.close, size: 32),
                label: const Text('Je refuse'),
              ),
            ),
          ],
        ],
      ),
    );
  }
}
