import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zarma_mobile/config/anon_id.dart';
import 'package:zarma_mobile/features/contribution/application/consent_controller.dart';
import 'package:zarma_mobile/features/contribution/data/contribution_withdrawal_repository.dart';
import 'package:zarma_mobile/widgets/brand_app_bar.dart';
import 'package:zarma_mobile/widgets/brand_footer.dart';

class PrivacyScreen extends ConsumerStatefulWidget {
  const PrivacyScreen({super.key});

  @override
  ConsumerState<PrivacyScreen> createState() => _PrivacyScreenState();
}

class _PrivacyScreenState extends ConsumerState<PrivacyScreen> {
  CancelToken? _cancelToken;
  bool _withdrawing = false;
  String? _message;

  Future<void> _requestWithdrawal() async {
    final bool? confirmed = await showDialog<bool>(
      context: context,
      builder: (BuildContext context) => AlertDialog(
        title: const Text('Retirer mes données vocales ?'),
        content: const Text(
          'Les fichiers audio encore actifs seront supprimés et leurs '
          'métadonnées anonymisées. L’application demandera ensuite un '
          'nouvel accord.',
        ),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Annuler'),
          ),
          FilledButton(
            key: const Key('confirm-privacy-withdrawal-button'),
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Retirer'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) {
      return;
    }

    setState(() {
      _withdrawing = true;
      _message = null;
    });
    final CancelToken token = CancelToken();
    _cancelToken = token;
    try {
      await ref.read(contributionWithdrawalRepositoryProvider).withdraw(
            anonId: ref.read(anonIdProvider),
            cancelToken: token,
          );
      if (!mounted) {
        return;
      }
      ref.read(consentStatusProvider.notifier).clearAcceptanceAfterWithdrawal();
      Navigator.of(context).popUntil((Route<dynamic> route) => route.isFirst);
    } on ContributionWithdrawalFailure catch (failure) {
      if (!mounted || failure.isCancelled) {
        return;
      }
      setState(() => _message = failure.message);
    } finally {
      _cancelToken = null;
      if (mounted) {
        setState(() => _withdrawing = false);
      }
    }
  }

  @override
  void dispose() {
    _cancelToken?.cancel('privacy_screen_disposed');
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final ConsentState consent = ref.watch(consentStatusProvider);
    return Scaffold(
      key: const Key('privacy-screen'),
      appBar: const BrandAppBar(title: 'Confidentialité'),
      bottomNavigationBar: const BrandFooter(),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(24, 16, 24, 24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              Expanded(
                child: SingleChildScrollView(
                  child: Text(
                    '${consent.content?.text ?? 'Politique indisponible.'}\n\n'
                    'Responsable : PTR Niger, Koubia, Niamey, Niger.\n'
                    'Contact : mail@ptrniger.com — +227 70 21 21 12.',
                    key: const Key('privacy-policy-text'),
                  ),
                ),
              ),
              if (_message != null) ...<Widget>[
                const SizedBox(height: 12),
                Text(
                  _message!,
                  key: const Key('privacy-withdrawal-error'),
                  textAlign: TextAlign.center,
                ),
              ],
              const SizedBox(height: 16),
              SizedBox(
                height: 64,
                child: FilledButton.icon(
                  key: const Key('request-privacy-withdrawal-button'),
                  onPressed: _withdrawing ? null : _requestWithdrawal,
                  icon: _withdrawing
                      ? const SizedBox.square(
                          dimension: 24,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.delete_forever_outlined, size: 32),
                  label: const Text('Retirer mes données vocales'),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
