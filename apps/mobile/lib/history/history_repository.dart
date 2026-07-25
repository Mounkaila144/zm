import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zarma_mobile/config/anon_id.dart';
import 'package:zarma_mobile/models/recognition_result.dart';
import 'package:zarma_mobile/network/api_client.dart';

/// Accès en lecture à l'historique des reconnaissances de l'utilisateur.
///
/// Appelle `GET /history?anon_id=<uuid>&limit=<n>` (baseUrl inclut déjà
/// `/api/v1`) et normalise les erreurs réseau via [normalizeNetworkFailure]
/// (messages sans détail interne).
class HistoryRepository {
  const HistoryRepository(this._dio);

  final Dio _dio;

  Future<List<RecognitionResult>> fetch({
    required String anonId,
    int limit = 50,
    CancelToken? cancelToken,
  }) async {
    try {
      final Response<List<dynamic>> response = await _dio.get<List<dynamic>>(
        '/history',
        queryParameters: <String, dynamic>{
          'anon_id': anonId,
          'limit': limit,
        },
        cancelToken: cancelToken,
      );
      final List<dynamic> data = response.data ?? <dynamic>[];
      return data
          .map((dynamic item) =>
              RecognitionResult.fromJson(item as Map<String, dynamic>))
          .toList(growable: false);
    } on DioException catch (exception) {
      throw normalizeNetworkFailure(exception);
    }
  }
}

final Provider<HistoryRepository> historyRepositoryProvider =
    Provider<HistoryRepository>((ref) {
  return HistoryRepository(ref.watch(dioProvider));
});

/// Historique de l'`anon_id` local. `autoDispose` libère le provider dès que
/// l'écran est quitté ; `ref.invalidate(historyProvider)` déclenche un réessai.
final AutoDisposeFutureProvider<List<RecognitionResult>> historyProvider =
    FutureProvider.autoDispose<List<RecognitionResult>>((ref) async {
  final HistoryRepository repository = ref.watch(historyRepositoryProvider);
  final String anonId = ref.watch(anonIdProvider);
  return repository.fetch(anonId: anonId);
});
