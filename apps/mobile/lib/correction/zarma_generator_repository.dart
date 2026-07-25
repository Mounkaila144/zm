import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zarma_mobile/network/api_client.dart';

/// Forme zarma canonique d'un nombre, générée **exclusivement** par le moteur
/// via l'API (`GET /grammar/generate/{n}`). Aucune règle numérique côté client.
class ZarmaGeneration {
  const ZarmaGeneration({
    required this.number,
    required this.zarmaText,
    required this.grammarVersion,
  });

  factory ZarmaGeneration.fromJson(Map<String, dynamic> json) {
    final Object? number = json['number'];
    final Object? zarmaText = json['zarma_text'];
    final Object? grammarVersion = json['grammar_version'];
    if (number is! num ||
        zarmaText is! String ||
        zarmaText.isEmpty ||
        grammarVersion is! String ||
        grammarVersion.isEmpty) {
      throw const GenerationContractException();
    }
    return ZarmaGeneration(
      number: number.toInt(),
      zarmaText: zarmaText,
      grammarVersion: grammarVersion,
    );
  }

  final int number;
  final String zarmaText;
  final String grammarVersion;
}

class GenerationContractException implements Exception {
  const GenerationContractException();
}

enum GenerationFailureType {
  outOfRange,
  unavailable,
  timeout,
  noConnection,
  cancelled,
  invalidResponse,
  unknown,
}

class GenerationFailure implements Exception {
  const GenerationFailure({
    required this.type,
    required this.message,
    this.statusCode,
    this.code,
  });

  final GenerationFailureType type;
  final String message;
  final int? statusCode;
  final String? code;

  bool get isCancelled => type == GenerationFailureType.cancelled;

  @override
  String toString() => message;
}

abstract interface class ZarmaGeneratorRepository {
  Future<ZarmaGeneration> generate({
    required int number,
    required CancelToken cancelToken,
  });
}

class DioZarmaGeneratorRepository implements ZarmaGeneratorRepository {
  const DioZarmaGeneratorRepository(this._dio);

  final Dio _dio;

  @override
  Future<ZarmaGeneration> generate({
    required int number,
    required CancelToken cancelToken,
  }) async {
    try {
      final Response<dynamic> response = await _dio.get<dynamic>(
        '/grammar/generate/$number',
        cancelToken: cancelToken,
      );
      final Object? data = response.data;
      if (data is! Map<String, dynamic>) {
        throw const GenerationContractException();
      }
      final ZarmaGeneration generation = ZarmaGeneration.fromJson(data);
      if (generation.number != number) {
        throw const GenerationContractException();
      }
      return generation;
    } on DioException catch (error) {
      throw _generationFailure(normalizeNetworkFailure(error));
    } on GenerationContractException {
      throw const GenerationFailure(
        type: GenerationFailureType.invalidResponse,
        message: 'La forme zarma reçue est invalide.',
      );
    }
  }
}

final zarmaGeneratorRepositoryProvider =
    Provider<ZarmaGeneratorRepository>((ref) {
  return DioZarmaGeneratorRepository(ref.watch(dioProvider));
});

GenerationFailure _generationFailure(NetworkFailure failure) {
  final int? status = failure.statusCode;
  final String? code = failure.code;
  final GenerationFailureType type;
  final String message;

  if (failure.type == NetworkFailureType.cancelled) {
    type = GenerationFailureType.cancelled;
    message = '';
  } else if (failure.type == NetworkFailureType.timeout ||
      failure.type == NetworkFailureType.noConnection) {
    type = failure.type == NetworkFailureType.timeout
        ? GenerationFailureType.timeout
        : GenerationFailureType.noConnection;
    message = 'Impossible de générer la forme zarma pour le moment.';
  } else if (code == 'OUT_OF_RANGE' || status == 400) {
    type = GenerationFailureType.outOfRange;
    message = 'Nombre hors plage. Choisissez un nombre entre 0 et 1 000 000.';
  } else if (code == 'UNRESOLVED_FORM') {
    type = GenerationFailureType.unavailable;
    message = 'Ce nombre n’a pas encore de forme zarma disponible.';
  } else if (status == 422) {
    type = GenerationFailureType.outOfRange;
    message = 'Nombre hors plage. Choisissez un nombre entre 0 et 1 000 000.';
  } else if (status == 500 || status == 503) {
    type = GenerationFailureType.unavailable;
    message = 'Le service est momentanément indisponible.';
  } else {
    type = GenerationFailureType.unknown;
    message = 'Impossible de générer la forme zarma pour le moment.';
  }

  return GenerationFailure(
    type: type,
    message: message,
    statusCode: status,
    code: code,
  );
}
