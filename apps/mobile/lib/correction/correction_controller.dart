import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zarma_mobile/correction/zarma_generator_repository.dart';
import 'package:zarma_mobile/recognition/recognition_controller.dart';

/// État de saisie de la correction : le nombre courant et la génération
/// asynchrone de sa forme zarma. `generation == null` signifie « pas encore de
/// saisie exploitable » (champ vide).
class CorrectionState {
  const CorrectionState({this.input = '', this.generation});

  final String input;
  final AsyncValue<ZarmaGeneration>? generation;

  /// Une correction n'est envoyable que si une forme zarma valide est prête.
  ZarmaGeneration? get ready => generation?.valueOrNull;
}

/// Débounce la saisie, applique un contrôle **léger** de plage pour un retour
/// immédiat, puis délègue au moteur (via l'API) la génération autoritaire de la
/// forme zarma. Aucune règle numérique n'est recalculée localement.
class CorrectionController extends StateNotifier<CorrectionState> {
  CorrectionController({
    required ZarmaGeneratorRepository repository,
    required CancelTokenFactory cancelTokenFactory,
    this.debounceDuration = const Duration(milliseconds: 300),
  })  : _repository = repository,
        _cancelTokenFactory = cancelTokenFactory,
        super(const CorrectionState());

  static const int maxValue = 1000000;

  final ZarmaGeneratorRepository _repository;
  final CancelTokenFactory _cancelTokenFactory;
  final Duration debounceDuration;

  Timer? _debounce;
  CancelToken? _cancelToken;

  void onInputChanged(String raw) {
    _debounce?.cancel();
    _cancelToken?.cancel('input_changed');

    final String digits = raw.trim();
    if (digits.isEmpty) {
      state = const CorrectionState();
      return;
    }

    final int? number = int.tryParse(digits);
    if (number == null || number < 0 || number > maxValue) {
      state = CorrectionState(
        input: digits,
        generation: const AsyncError<ZarmaGeneration>(
          GenerationFailure(
            type: GenerationFailureType.outOfRange,
            message:
                'Nombre hors plage. Choisissez un nombre entre 0 et 1 000 000.',
          ),
          StackTrace.empty,
        ),
      );
      return;
    }

    state = CorrectionState(
      input: digits,
      generation: const AsyncLoading<ZarmaGeneration>(),
    );
    _debounce = Timer(debounceDuration, () => _generate(number));
  }

  Future<void> _generate(int number) async {
    final CancelToken token = _cancelTokenFactory();
    _cancelToken = token;
    try {
      final ZarmaGeneration generation = await _repository.generate(
        number: number,
        cancelToken: token,
      );
      if (!mounted || _cancelToken != token) {
        return;
      }
      state = CorrectionState(
        input: state.input,
        generation: AsyncData<ZarmaGeneration>(generation),
      );
    } on GenerationFailure catch (failure) {
      if (!mounted || failure.isCancelled || _cancelToken != token) {
        return;
      }
      state = CorrectionState(
        input: state.input,
        generation: AsyncError<ZarmaGeneration>(failure, StackTrace.empty),
      );
    }
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _cancelToken?.cancel('screen_disposed');
    super.dispose();
  }
}

final correctionControllerProvider =
    StateNotifierProvider.autoDispose<CorrectionController, CorrectionState>(
        (ref) {
  return CorrectionController(
    repository: ref.watch(zarmaGeneratorRepositoryProvider),
    cancelTokenFactory: ref.watch(cancelTokenFactoryProvider),
  );
});
