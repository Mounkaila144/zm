import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zarma_mobile/correction/zarma_generator_repository.dart';
import 'package:zarma_mobile/features/contribution/data/contribution_prompt_catalog.dart';
import 'package:zarma_mobile/features/contribution/models/contribution_models.dart';

enum ContributionPromptFailureType {
  timeout,
  noConnection,
  cancelled,
  invalidResponse,
  unavailable,
}

class ContributionPromptFailure implements Exception {
  const ContributionPromptFailure({
    required this.type,
    required this.message,
  });

  final ContributionPromptFailureType type;
  final String message;

  bool get isCancelled => type == ContributionPromptFailureType.cancelled;

  @override
  String toString() => message;
}

abstract interface class ContributionPromptRepository {
  Future<ContributionPrompt> nextPrompt({
    required CancelToken cancelToken,
  });
}

class ApiContributionPromptRepository implements ContributionPromptRepository {
  const ApiContributionPromptRepository({
    required ContributionPromptSource source,
    required ZarmaGeneratorRepository generator,
  })  : _source = source,
        _generator = generator;

  final ContributionPromptSource _source;
  final ZarmaGeneratorRepository _generator;

  @override
  Future<ContributionPrompt> nextPrompt({
    required CancelToken cancelToken,
  }) async {
    final ContributionPromptSeed seed = _source.next();
    try {
      final ZarmaGeneration generation = await _generator.generate(
        number: seed.number,
        cancelToken: cancelToken,
      );
      return ContributionPrompt(
        expectedNumber: generation.number,
        expectedPrompt: generation.zarmaText,
        category: seed.category,
        grammarVersion: generation.grammarVersion,
      );
    } on GenerationFailure catch (failure) {
      throw _mapFailure(failure);
    }
  }
}

final contributionPromptRepositoryProvider =
    Provider<ContributionPromptRepository>((ref) {
  return ApiContributionPromptRepository(
    source: ref.watch(contributionPromptSourceProvider),
    generator: ref.watch(zarmaGeneratorRepositoryProvider),
  );
});

ContributionPromptFailure _mapFailure(GenerationFailure failure) {
  switch (failure.type) {
    case GenerationFailureType.timeout:
      return const ContributionPromptFailure(
        type: ContributionPromptFailureType.timeout,
        message: 'Le serveur met trop de temps à proposer un nombre.',
      );
    case GenerationFailureType.noConnection:
      return const ContributionPromptFailure(
        type: ContributionPromptFailureType.noConnection,
        message: 'Impossible de charger un nombre à prononcer.',
      );
    case GenerationFailureType.cancelled:
      return const ContributionPromptFailure(
        type: ContributionPromptFailureType.cancelled,
        message: '',
      );
    case GenerationFailureType.invalidResponse:
      return const ContributionPromptFailure(
        type: ContributionPromptFailureType.invalidResponse,
        message: 'Le nombre proposé est momentanément indisponible.',
      );
    case GenerationFailureType.outOfRange:
    case GenerationFailureType.unavailable:
    case GenerationFailureType.unknown:
      return const ContributionPromptFailure(
        type: ContributionPromptFailureType.unavailable,
        message: 'Impossible de proposer un nombre pour le moment.',
      );
  }
}
