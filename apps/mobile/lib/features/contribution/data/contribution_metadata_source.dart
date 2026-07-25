import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zarma_mobile/features/contribution/models/contribution_models.dart';

abstract interface class ContributionMetadataSource {
  Future<ContributionMetadata> load();
}

/// Source par défaut respectueuse de la vie privée : aucune collecte implicite.
class EmptyContributionMetadataSource implements ContributionMetadataSource {
  const EmptyContributionMetadataSource();

  @override
  Future<ContributionMetadata> load() async {
    return const ContributionMetadata();
  }
}

final contributionMetadataSourceProvider =
    Provider<ContributionMetadataSource>((ref) {
  return const EmptyContributionMetadataSource();
});
