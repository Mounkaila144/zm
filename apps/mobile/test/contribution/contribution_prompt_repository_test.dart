import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:zarma_mobile/correction/zarma_generator_repository.dart';
import 'package:zarma_mobile/features/contribution/data/contribution_prompt_catalog.dart';
import 'package:zarma_mobile/features/contribution/data/contribution_prompt_repository.dart';
import 'package:zarma_mobile/features/contribution/models/contribution_models.dart';

class _FixedPromptSource implements ContributionPromptSource {
  @override
  ContributionPromptSeed next() {
    return const ContributionPromptSeed(
      number: 100,
      category: ContributionPromptCategory.asrConfusion,
    );
  }
}

class _FakeGenerator implements ZarmaGeneratorRepository {
  GenerationFailure? failure;

  @override
  Future<ZarmaGeneration> generate({
    required int number,
    required CancelToken cancelToken,
  }) async {
    if (failure != null) {
      throw failure!;
    }
    return const ZarmaGeneration(
      number: 100,
      zarmaText: 'zangou',
      grammarVersion: '1.1.0',
    );
  }
}

void main() {
  late _FakeGenerator generator;
  late ApiContributionPromptRepository repository;

  setUp(() {
    generator = _FakeGenerator();
    repository = ApiContributionPromptRepository(
      source: _FixedPromptSource(),
      generator: generator,
    );
  });

  test('résout forme, version et catégorie sans règle Dart', () async {
    final ContributionPrompt prompt = await repository.nextPrompt(
      cancelToken: CancelToken(),
    );

    expect(prompt.expectedNumber, 100);
    expect(prompt.expectedPrompt, 'zangou');
    expect(prompt.grammarVersion, '1.1.0');
    expect(prompt.category, ContributionPromptCategory.asrConfusion);
  });

  for (final MapEntry<GenerationFailureType,
          ContributionPromptFailureType> scenario
      in const <GenerationFailureType, ContributionPromptFailureType>{
    GenerationFailureType.timeout: ContributionPromptFailureType.timeout,
    GenerationFailureType.noConnection:
        ContributionPromptFailureType.noConnection,
    GenerationFailureType.invalidResponse:
        ContributionPromptFailureType.invalidResponse,
    GenerationFailureType.unavailable:
        ContributionPromptFailureType.unavailable,
  }.entries) {
    test('normalise ${scenario.key.name} vers un message sûr', () async {
      generator.failure = GenerationFailure(
        type: scenario.key,
        message: 'détail interne à ne pas exposer',
      );

      await expectLater(
        repository.nextPrompt(cancelToken: CancelToken()),
        throwsA(
          isA<ContributionPromptFailure>()
              .having(
                (ContributionPromptFailure failure) => failure.type,
                'type',
                scenario.value,
              )
              .having(
                (ContributionPromptFailure failure) => failure.message,
                'message',
                isNot(contains('détail interne')),
              ),
        ),
      );
    });
  }
}
