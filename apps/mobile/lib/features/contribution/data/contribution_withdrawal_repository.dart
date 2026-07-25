import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zarma_mobile/network/api_client.dart';

enum ContributionWithdrawalFailureType {
  timeout,
  noConnection,
  cancelled,
  rateLimited,
  incomplete,
  serviceUnavailable,
  invalidResponse,
}

class ContributionWithdrawalFailure implements Exception {
  const ContributionWithdrawalFailure({
    required this.type,
    required this.message,
    this.statusCode,
    this.code,
    this.requestId,
  });

  final ContributionWithdrawalFailureType type;
  final String message;
  final int? statusCode;
  final String? code;
  final String? requestId;

  bool get isCancelled => type == ContributionWithdrawalFailureType.cancelled;

  @override
  String toString() => message;
}

abstract interface class ContributionWithdrawalRepository {
  Future<void> withdraw({
    required String anonId,
    required CancelToken cancelToken,
  });
}

class DioContributionWithdrawalRepository
    implements ContributionWithdrawalRepository {
  const DioContributionWithdrawalRepository(this._dio);

  final Dio _dio;

  @override
  Future<void> withdraw({
    required String anonId,
    required CancelToken cancelToken,
  }) async {
    try {
      final Response<dynamic> response = await _dio.post<dynamic>(
        '/recordings/withdraw',
        data: <String, dynamic>{'anon_id': anonId},
        cancelToken: cancelToken,
      );
      final Object? data = response.data;
      if (data is! Map<String, dynamic> ||
          data.length != 1 ||
          data['status'] != 'withdrawn') {
        throw const ContributionWithdrawalFailure(
          type: ContributionWithdrawalFailureType.invalidResponse,
          message: 'Le reçu de retrait est invalide.',
        );
      }
    } on DioException catch (error) {
      throw _withdrawalFailure(normalizeNetworkFailure(error));
    } on ContributionWithdrawalFailure {
      rethrow;
    } catch (_) {
      throw const ContributionWithdrawalFailure(
        type: ContributionWithdrawalFailureType.invalidResponse,
        message: 'Le reçu de retrait est invalide.',
      );
    }
  }
}

final contributionWithdrawalRepositoryProvider =
    Provider<ContributionWithdrawalRepository>((ref) {
  return DioContributionWithdrawalRepository(ref.watch(dioProvider));
});

ContributionWithdrawalFailure _withdrawalFailure(NetworkFailure failure) {
  final int? status = failure.statusCode;
  final String? code = failure.code;
  final ContributionWithdrawalFailureType type;
  final String message;

  if (failure.type == NetworkFailureType.cancelled) {
    type = ContributionWithdrawalFailureType.cancelled;
    message = 'Retrait annulé.';
  } else if (failure.type == NetworkFailureType.timeout) {
    type = ContributionWithdrawalFailureType.timeout;
    message = 'Le retrait a pris trop de temps. Réessayez.';
  } else if (failure.type == NetworkFailureType.noConnection) {
    type = ContributionWithdrawalFailureType.noConnection;
    message = 'Impossible de joindre le serveur. Réessayez.';
  } else if (status == 429 || code == 'RATE_LIMITED') {
    type = ContributionWithdrawalFailureType.rateLimited;
    message = 'Trop de demandes. Patientez avant de réessayer.';
  } else if (status == 503 || code == 'WITHDRAWAL_INCOMPLETE') {
    type = ContributionWithdrawalFailureType.incomplete;
    message = 'Le retrait est incomplet. Réessayez pour le terminer.';
  } else if (status == 500) {
    type = ContributionWithdrawalFailureType.serviceUnavailable;
    message = 'Le service de retrait est momentanément indisponible.';
  } else {
    type = ContributionWithdrawalFailureType.serviceUnavailable;
    message = 'Le retrait n’a pas pu être terminé.';
  }

  return ContributionWithdrawalFailure(
    type: type,
    message: message,
    statusCode: status,
    code: code,
    requestId: failure.requestId,
  );
}
