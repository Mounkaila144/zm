import 'dart:math';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zarma_mobile/features/contribution/models/contribution_models.dart';

class ContributionPromptSeed {
  const ContributionPromptSeed({
    required this.number,
    required this.category,
  });

  final int number;
  final ContributionPromptCategory category;
}

/// Catalogue de nombres uniquement : aucune règle nombre→zarma n'est dupliquée
/// côté Flutter. La forme canonique est résolue ensuite par l'API de grammaire.
const List<ContributionPromptSeed> contributionPromptCatalog =
    <ContributionPromptSeed>[
  ContributionPromptSeed(
    number: 0,
    category: ContributionPromptCategory.scaleOrBoundary,
  ),
  ContributionPromptSeed(
    number: 1,
    category: ContributionPromptCategory.unitOrTen,
  ),
  ContributionPromptSeed(
    number: 7,
    category: ContributionPromptCategory.unitOrTen,
  ),
  ContributionPromptSeed(
    number: 10,
    category: ContributionPromptCategory.unitOrTen,
  ),
  ContributionPromptSeed(
    number: 90,
    category: ContributionPromptCategory.unitOrTen,
  ),
  ContributionPromptSeed(
    number: 11,
    category: ContributionPromptCategory.composition,
  ),
  ContributionPromptSeed(
    number: 27,
    category: ContributionPromptCategory.composition,
  ),
  ContributionPromptSeed(
    number: 99,
    category: ContributionPromptCategory.composition,
  ),
  ContributionPromptSeed(
    number: 100,
    category: ContributionPromptCategory.asrConfusion,
  ),
  ContributionPromptSeed(
    number: 205,
    category: ContributionPromptCategory.hundred,
  ),
  ContributionPromptSeed(
    number: 999,
    category: ContributionPromptCategory.hundred,
  ),
  ContributionPromptSeed(
    number: 1000,
    category: ContributionPromptCategory.thousand,
  ),
  ContributionPromptSeed(
    number: 1005,
    category: ContributionPromptCategory.thousand,
  ),
  ContributionPromptSeed(
    number: 9999,
    category: ContributionPromptCategory.thousand,
  ),
  ContributionPromptSeed(
    number: 10000,
    category: ContributionPromptCategory.scaleOrBoundary,
  ),
  ContributionPromptSeed(
    number: 100000,
    category: ContributionPromptCategory.scaleOrBoundary,
  ),
  ContributionPromptSeed(
    number: 999999,
    category: ContributionPromptCategory.scaleOrBoundary,
  ),
  ContributionPromptSeed(
    number: 1000000,
    category: ContributionPromptCategory.scaleOrBoundary,
  ),
];

typedef PromptIndexSelector = int Function(int upperBound);

abstract interface class ContributionPromptSource {
  ContributionPromptSeed next();
}

class CatalogContributionPromptSource implements ContributionPromptSource {
  CatalogContributionPromptSource({
    required this._selector,
    List<ContributionPromptSeed> catalog = contributionPromptCatalog,
  })  : _catalog = List<ContributionPromptSeed>.unmodifiable(catalog) {
    if (_catalog.isEmpty) {
      throw ArgumentError.value(catalog, 'catalog', 'ne peut pas être vide');
    }
  }

  final PromptIndexSelector _selector;
  final List<ContributionPromptSeed> _catalog;
  int? _previousIndex;

  @override
  ContributionPromptSeed next() {
    final int selected = _selector(_catalog.length);
    int index = selected.remainder(_catalog.length);
    if (index < 0) {
      index += _catalog.length;
    }
    if (_catalog.length > 1 && index == _previousIndex) {
      index = (index + 1) % _catalog.length;
    }
    _previousIndex = index;
    return _catalog[index];
  }
}

final promptIndexSelectorProvider = Provider<PromptIndexSelector>((ref) {
  final Random random = Random.secure();
  return random.nextInt;
});

final contributionPromptSourceProvider =
    Provider<ContributionPromptSource>((ref) {
  return CatalogContributionPromptSource(
    selector: ref.watch(promptIndexSelectorProvider),
  );
});
