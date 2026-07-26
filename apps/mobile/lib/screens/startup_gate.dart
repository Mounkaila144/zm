import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zarma_mobile/features/contribution/application/consent_controller.dart';
import 'package:zarma_mobile/features/contribution/presentation/consent_screen.dart';
import 'package:zarma_mobile/screens/home_screen.dart';
import 'package:zarma_mobile/theme/brand.dart';
import 'package:zarma_mobile/update/mobile_update.dart';
import 'package:zarma_mobile/widgets/brand_app_bar.dart';
import 'package:zarma_mobile/widgets/brand_footer.dart';

class StartupGate extends ConsumerWidget {
  const StartupGate({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final AsyncValue<MobileUpdatePolicy> policy =
        ref.watch(mobileUpdatePolicyProvider);
    return policy.when(
      loading: () => const _StartupLoading(),
      error: (_, __) => _StartupError(
        onRetry: () => ref.invalidate(mobileUpdatePolicyProvider),
      ),
      data: (MobileUpdatePolicy value) {
        if (value.updateRequired) {
          return _UpdateRequiredScreen(policy: value);
        }
        final ConsentState consent = ref.watch(consentStatusProvider);
        return consent.hasValidConsent
            ? const HomeScreen()
            : const ConsentScreen(mandatory: true);
      },
    );
  }
}

class _StartupLoading extends StatelessWidget {
  const _StartupLoading();

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      body: Center(child: CircularProgressIndicator()),
    );
  }
}

class _StartupError extends StatelessWidget {
  const _StartupError({required this.onRetry});

  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: const BrandAppBar(
        title: 'Connexion',
        automaticallyImplyLeading: false,
      ),
      bottomNavigationBar: const BrandFooter(),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: FilledButton.icon(
            key: const Key('retry-startup-button'),
            onPressed: onRetry,
            icon: const Icon(Icons.refresh, size: 40),
            label: const Text('Réessayer'),
          ),
        ),
      ),
    );
  }
}

class _UpdateRequiredScreen extends ConsumerStatefulWidget {
  const _UpdateRequiredScreen({required this.policy});

  final MobileUpdatePolicy policy;

  @override
  ConsumerState<_UpdateRequiredScreen> createState() =>
      _UpdateRequiredScreenState();
}

class _UpdateRequiredScreenState extends ConsumerState<_UpdateRequiredScreen> {
  bool _starting = false;
  bool _unavailable = false;

  Future<void> _update() async {
    if (_starting) {
      return;
    }
    setState(() {
      _starting = true;
      _unavailable = false;
    });
    final bool started = await ref
        .read(immediateUpdateGatewayProvider)
        .start(playStoreUrl: widget.policy.playStoreUrl);
    if (!mounted) {
      return;
    }
    setState(() {
      _starting = false;
      _unavailable = !started;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      key: const Key('update-required-screen'),
      appBar: const BrandAppBar(
        title: 'Mise à jour',
        automaticallyImplyLeading: false,
      ),
      bottomNavigationBar: const BrandFooter(),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: <Widget>[
              const Icon(
                Icons.system_update_alt,
                size: 112,
                color: BrandColors.red,
              ),
              const SizedBox(height: 24),
              Text(
                'Une mise à jour est nécessaire.',
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.headlineSmall,
              ),
              if (_unavailable) ...<Widget>[
                const SizedBox(height: 16),
                const Text(
                  'Ouvrez cette application depuis Google Play, puis réessayez.',
                  textAlign: TextAlign.center,
                ),
              ],
              const SizedBox(height: 32),
              SizedBox(
                width: double.infinity,
                height: 76,
                child: FilledButton.icon(
                  key: const Key('mandatory-update-button'),
                  onPressed: _starting ? null : _update,
                  icon: _starting
                      ? const SizedBox.square(
                          dimension: 28,
                          child: CircularProgressIndicator(strokeWidth: 3),
                        )
                      : const Icon(Icons.download, size: 40),
                  label: const Text('Mettre à jour'),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
