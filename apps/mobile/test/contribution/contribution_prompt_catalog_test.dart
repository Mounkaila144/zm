import 'package:flutter_test/flutter_test.dart';
import 'package:zarma_mobile/features/contribution/data/contribution_prompt_catalog.dart';
import 'package:zarma_mobile/features/contribution/models/contribution_models.dart';

void main() {
  test('le catalogue couvre la plage, les échelles et la confusion ASR', () {
    expect(
      contributionPromptCatalog.every(
        (ContributionPromptSeed seed) =>
            seed.number >= 0 && seed.number <= 1000000,
      ),
      isTrue,
    );
    expect(
      contributionPromptCatalog
          .map((ContributionPromptSeed seed) => seed.category)
          .toSet(),
      containsAll(ContributionPromptCategory.values),
    );
    expect(
      contributionPromptCatalog
          .map((ContributionPromptSeed seed) => seed.number),
      containsAll(<int>[0, 10, 99, 100, 1000, 10000, 100000, 1000000]),
    );

    final List<ContributionPromptSeed> confusionSeeds =
        contributionPromptCatalog
            .where(
              (ContributionPromptSeed seed) =>
                  seed.category == ContributionPromptCategory.asrConfusion,
            )
            .toList();
    // 100 est résolu côté API en une forme contenant « zangou », terme
    // canonique visé par la paire acoustique zangu→zangou du lexique.
    expect(confusionSeeds.map((ContributionPromptSeed seed) => seed.number),
        contains(100));
  });

  test('la sélection injectée est déterministe et évite une répétition', () {
    final CatalogContributionPromptSource source =
        CatalogContributionPromptSource(
      selector: (_) => 0,
      catalog: const <ContributionPromptSeed>[
        ContributionPromptSeed(
          number: 1,
          category: ContributionPromptCategory.unitOrTen,
        ),
        ContributionPromptSeed(
          number: 2,
          category: ContributionPromptCategory.unitOrTen,
        ),
      ],
    );

    expect(source.next().number, 1);
    expect(source.next().number, 2);
    expect(source.next().number, 1);
  });
}
