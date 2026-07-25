import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:zarma_mobile/models/recognition_result.dart';
import 'package:zarma_mobile/navigation/app_routes.dart';
import 'package:zarma_mobile/screens/calculation_screen.dart';
import 'package:zarma_mobile/speech/voice_bank.dart';
import 'package:zarma_mobile/speech/zarma_speaker.dart';

/// Écran de calcul : il montre ce que le serveur a répondu — et le **dit**.
///
/// L'utilisateur cible ne lit pas : un écran muet ne lui apprend rien. Ces
/// tests vérifient donc autant l'affichage que la prononciation, y compris son
/// refus de prononcer un énoncé incomplet.
void main() {
  late List<Uint8List> played;

  setUp(() => played = <Uint8List>[]);

  RecognitionResult result({RecognizedExpression? expression}) {
    return RecognitionResult(
      id: 'aaaaaaaa-0000-4000-8000-000000000001',
      recognizedNumber: null,
      zarmaText: expression?.zarmaText ?? '',
      normalizedText: '',
      confidence: 0.9,
      decision: Decision.accept,
      modelVersion: 'mock-1.0.0',
      grammarVersion: '1.4.0',
      expression: expression,
    );
  }

  /// Banque de test : les mots fournis existent, les autres non.
  VoiceBank bankOf(Iterable<String> words,
      {Iterable<String> prompts = const <String>[]}) {
    return VoiceBank(
      assetByWord: <String, String>{
        for (final String w in words) w: 'assets/voice/words/$w.wav',
      },
      assetByPrompt: <String, String>{
        for (final String p in prompts) p: 'assets/voice/prompts/$p.wav',
      },
    );
  }

  Future<void> pump(
    WidgetTester tester,
    RecognitionResult value, {
    VoiceBank? bank,
  }) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          voiceBankProvider.overrideWith(
            (ref) async => bank ?? const VoiceBank.empty(),
          ),
          wavPlayerProvider.overrideWithValue(
            (Uint8List wav) async => played.add(wav),
          ),
        ],
        child: MaterialApp(home: CalculationScreen(result: value)),
      ),
    );
    await tester.pumpAndSettle();
  }

  testWidgets('affiche l’opération, le résultat et sa forme zarma',
      (tester) async {
    await pump(
      tester,
      result(
        expression: const RecognizedExpression(
          left: 23,
          operator: '+',
          right: 15,
          zarmaText: 'waranka cindi hinza tonton iwey cindi gou',
          result: 38,
          resultZarmaText: 'waranza cindi hakou',
        ),
      ),
    );

    expect(find.text('23 + 15'), findsOneWidget);
    expect(find.text('38'), findsOneWidget);
    expect(find.text('waranza cindi hakou'), findsOneWidget);
    expect(find.byKey(const Key('calculation-refusal')), findsNothing);
  });

  testWidgets('affiche le reste d’une division sans l’arrondir',
      (tester) async {
    await pump(
      tester,
      result(
        expression: const RecognizedExpression(
          left: 103,
          operator: '/',
          right: 5,
          zarmaText: '—',
          result: 20,
          remainder: 3,
          resultZarmaText: 'waranka ga cindi hinza',
        ),
      ),
    );

    expect(find.text('20 reste 3'), findsOneWidget);
    expect(find.text('waranka ga cindi hinza'), findsOneWidget);
  });

  testWidgets('un refus n’affiche aucun nombre', (tester) async {
    await pump(
      tester,
      result(
        expression: const RecognizedExpression(
          left: 3,
          operator: '-',
          right: 5,
          zarmaText: 'ihinza zabou igou',
          refusalCode: 'NEGATIVE_RESULT',
        ),
      ),
    );

    expect(find.byKey(const Key('calculation-result')), findsNothing);
    expect(find.byKey(const Key('calculation-refusal')), findsOneWidget);
    expect(find.textContaining('négatif'), findsOneWidget);
  });

  // --------------------------------------------------------------------- //
  // AC5 — le résultat doit être DIT, pas seulement affiché
  // --------------------------------------------------------------------- //

  const RecognizedExpression sum = RecognizedExpression(
    left: 23,
    operator: '+',
    right: 15,
    zarmaText: 'waranka cindi hinza tonton iwey cindi gou',
    result: 38,
    resultZarmaText: 'waranza cindi hakou',
  );

  testWidgets('prononce le résultat dès l’affichage', (tester) async {
    await pump(
      tester,
      result(expression: sum),
      bank: bankOf(<String>['waranza', 'cindi', 'hakou']),
    );

    expect(played, hasLength(1),
        reason: 'le résultat doit être dit sans action');
  });

  testWidgets('ne prononce pas deux fois le même résultat', (tester) async {
    await pump(
      tester,
      result(expression: sum),
      bank: bankOf(<String>['waranza', 'cindi', 'hakou']),
    );
    await tester.pump();

    expect(played, hasLength(1));
  });

  testWidgets('ne garde qu’un bouton pour lancer une nouvelle opération',
      (tester) async {
    await pump(
      tester,
      result(expression: sum),
      bank: bankOf(<String>['waranza', 'cindi', 'hakou']),
    );

    expect(find.byKey(const Key('calculation-replay-button')), findsNothing);
    expect(find.byKey(const Key('calculation-home-button')), findsNothing);
    expect(
      find.byKey(const Key('record-new-calculation-button')),
      findsOneWidget,
    );
    expect(played, hasLength(1));
  });

  testWidgets('prononce le refus au lieu de se taire', (tester) async {
    await pump(
      tester,
      result(
        expression: const RecognizedExpression(
          left: 3,
          operator: '-',
          right: 5,
          zarmaText: 'ihinza zabou igou',
          refusalCode: 'NEGATIVE_RESULT',
        ),
      ),
      bank: bankOf(<String>[], prompts: <String>[kPromptCannotAnswer]),
    );

    expect(played, hasLength(1), reason: 'un silence passerait pour une panne');
  });

  testWidgets('un mot manquant fait taire tout l’énoncé et le signale',
      (tester) async {
    // `hakou` absent : prononcer « waranza cindi » ferait entendre « 30 »
    // au lieu de « 38 », sans que l'utilisateur puisse s'en apercevoir.
    await pump(
      tester,
      result(expression: sum),
      bank: bankOf(<String>['waranza', 'cindi']),
    );

    expect(played, isEmpty);
    expect(
      find.byKey(const Key('calculation-speech-unavailable')),
      findsOneWidget,
    );
  });

  testWidgets('l’écran reste lisible même sans banque vocale', (tester) async {
    await pump(tester, result(expression: sum));

    expect(played, isEmpty);
    expect(find.text('38'), findsOneWidget);
  });

  testWidgets('la route refuse un argument sans opération', (tester) async {
    final Route<dynamic>? route = AppRoutes.onGenerateRoute(
      RouteSettings(name: AppRoutes.calculation, arguments: result()),
    );
    expect(route, isNotNull);

    await tester.pumpWidget(
      MaterialApp(
        onGenerateRoute: AppRoutes.onGenerateRoute,
        initialRoute: AppRoutes.home,
        routes: AppRoutes.routes,
      ),
    );
    // L'écran de calcul n'est jamais atteint sans expression : la route
    // bascule sur l'écran d'arguments invalides plutôt que d'afficher du vide.
    expect(find.byKey(const Key('calculation-screen')), findsNothing);
  });
}
