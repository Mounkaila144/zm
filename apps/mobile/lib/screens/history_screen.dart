import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zarma_mobile/history/history_repository.dart';
import 'package:zarma_mobile/models/recognition_result.dart';
import 'package:zarma_mobile/network/api_client.dart';
import 'package:zarma_mobile/widgets/brand_app_bar.dart';
import 'package:zarma_mobile/widgets/brand_footer.dart';
import 'package:zarma_mobile/widgets/zarma_number_display.dart';

/// Écran Historique : liste des reconnaissances récentes de l'`anon_id` local.
///
/// Gère les trois états via `AsyncValue.when` : chargement (indicateur),
/// erreur (message clair + réessai `ref.invalidate`) et données (liste ou
/// message « aucune reconnaissance »). Le chargement est non bloquant ; le
/// réessai couvre les connexions lentes (AC2/AC3).
class HistoryScreen extends ConsumerWidget {
  const HistoryScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final AsyncValue<List<RecognitionResult>> history =
        ref.watch(historyProvider);

    return Scaffold(
      key: const Key('history-screen'),
      appBar: const BrandAppBar(title: 'Historique'),
      bottomNavigationBar: const BrandFooter(),
      body: history.when(
        loading: () => const Center(
          child: CircularProgressIndicator(key: Key('history-loading')),
        ),
        error: (Object error, StackTrace _) => _HistoryError(
          message: _messageFor(error),
          onRetry: () => ref.invalidate(historyProvider),
        ),
        data: (List<RecognitionResult> items) =>
            items.isEmpty ? const _HistoryEmpty() : _HistoryList(items: items),
      ),
    );
  }
}

String _messageFor(Object error) =>
    error is NetworkFailure ? error.message : 'Une erreur est survenue.';

class _HistoryList extends StatelessWidget {
  const _HistoryList({required this.items});

  final List<RecognitionResult> items;

  @override
  Widget build(BuildContext context) {
    return ListView.separated(
      key: const Key('history-list'),
      itemCount: items.length,
      separatorBuilder: (_, __) => const Divider(height: 1),
      itemBuilder: (BuildContext context, int index) {
        final RecognitionResult item = items[index];
        final String date = _formatDate(item.createdAt);
        return ListTile(
          key: Key('history-item-$index'),
          title: ZarmaNumberDisplay(number: item.recognizedNumber),
          trailing: date.isEmpty
              ? null
              : Text(date, style: Theme.of(context).textTheme.bodySmall),
        );
      },
    );
  }
}

class _HistoryEmpty extends StatelessWidget {
  const _HistoryEmpty();

  @override
  Widget build(BuildContext context) {
    return const Center(
      key: Key('history-empty'),
      child: Text('Aucune reconnaissance pour le moment.'),
    );
  }
}

class _HistoryError extends StatelessWidget {
  const _HistoryError({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      key: const Key('history-error'),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Text(message, textAlign: TextAlign.center),
          const SizedBox(height: 16),
          FilledButton(
            key: const Key('history-retry'),
            onPressed: onRetry,
            child: const Text('Réessayer'),
          ),
        ],
      ),
    );
  }
}

String _formatDate(DateTime? value) {
  if (value == null) {
    return '';
  }
  final DateTime local = value.toLocal();
  String two(int n) => n.toString().padLeft(2, '0');
  return '${local.year}-${two(local.month)}-${two(local.day)} '
      '${two(local.hour)}:${two(local.minute)}';
}
