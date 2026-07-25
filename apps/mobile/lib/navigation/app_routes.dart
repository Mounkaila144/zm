import 'package:flutter/material.dart';
import 'package:zarma_mobile/feedback/feedback_models.dart';
import 'package:zarma_mobile/features/contribution/presentation/contribution_route.dart';
import 'package:zarma_mobile/models/recognition_result.dart';
import 'package:zarma_mobile/recording/audio_recording_models.dart';
import 'package:zarma_mobile/screens/calculation_screen.dart';
import 'package:zarma_mobile/screens/confirmation_screen.dart';
import 'package:zarma_mobile/screens/correction_screen.dart';
import 'package:zarma_mobile/screens/history_screen.dart';
import 'package:zarma_mobile/screens/home_screen.dart';
import 'package:zarma_mobile/screens/processing_screen.dart';
import 'package:zarma_mobile/screens/recording_screen.dart';
import 'package:zarma_mobile/screens/result_screen.dart';

abstract final class AppRoutes {
  static const String home = '/';
  static const String recording = '/recording';
  static const String processing = '/processing';
  static const String result = '/result';

  /// Résultat d'une **opération** (story 6.1) — distinct de [result], qui
  /// affiche un nombre seul.
  static const String calculation = '/calculation';
  static const String confirmation = '/confirmation';
  static const String correction = '/correction';
  static const String history = '/history';
  static const String contribute = '/contribute';

  static final Map<String, WidgetBuilder> routes = <String, WidgetBuilder>{
    home: (_) => const HomeScreen(),
    recording: (_) => const RecordingScreen(),
    history: (_) => const HistoryScreen(),
    contribute: (_) => const ContributionRoute(),
  };

  static Route<dynamic>? onGenerateRoute(RouteSettings settings) {
    final Widget child;
    switch (settings.name) {
      case processing:
        final Object? arguments = settings.arguments;
        child = arguments is AudioHandoff
            ? ProcessingScreen(handoff: arguments)
            : const _InvalidArgumentsScreen();
      case result:
        final Object? arguments = settings.arguments;
        if (arguments is ConfirmedResult) {
          child = ResultScreen(
            result: arguments.recognition,
            confirmed: arguments,
          );
        } else if (arguments is RecognitionResult &&
            arguments.decision == Decision.accept &&
            arguments.recognizedNumber != null &&
            arguments.zarmaText.trim().isNotEmpty) {
          child = ResultScreen(result: arguments);
        } else {
          child = const _InvalidArgumentsScreen();
        }
      case calculation:
        final Object? arguments = settings.arguments;
        child = arguments is RecognitionResult && arguments.expression != null
            ? CalculationScreen(result: arguments)
            : const _InvalidArgumentsScreen();
      case confirmation:
        final Object? arguments = settings.arguments;
        child = arguments is RecognitionResult
            ? ConfirmationScreen(result: arguments)
            : const _InvalidArgumentsScreen();
      case correction:
        final Object? arguments = settings.arguments;
        child = arguments is RecognitionResult
            ? CorrectionScreen(result: arguments)
            : const _InvalidArgumentsScreen();
      default:
        return null;
    }
    return MaterialPageRoute<dynamic>(
      builder: (_) => child,
      settings: settings,
    );
  }
}

class _InvalidArgumentsScreen extends StatelessWidget {
  const _InvalidArgumentsScreen();

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      key: const Key('invalid-route-arguments-screen'),
      appBar: AppBar(title: const Text('Navigation impossible')),
      body: Center(
        child: FilledButton.icon(
          onPressed: () =>
              Navigator.of(context).popUntil((Route<dynamic> route) {
            return route.isFirst;
          }),
          icon: const Icon(Icons.home_outlined),
          label: const Text('Retour à l’Accueil'),
        ),
      ),
    );
  }
}
