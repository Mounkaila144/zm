import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

class AppConfig {
  const AppConfig({
    required this.apiBaseUrl,
    this.connectTimeout = const Duration(seconds: 10),
    this.sendTimeout = const Duration(seconds: 30),
    this.receiveTimeout = const Duration(seconds: 30),
  });

  factory AppConfig.fromEnvironment() {
    const String configuredApiBaseUrl = String.fromEnvironment('API_BASE_URL');
    final String defaultApiBaseUrl = defaultTargetPlatform == TargetPlatform.iOS
        ? 'https://ia.ptrniger.com/api/v1'
        : 'http://10.0.2.2:8000/api/v1';

    return AppConfig(
      apiBaseUrl: configuredApiBaseUrl.isEmpty
          ? defaultApiBaseUrl
          : configuredApiBaseUrl,
    );
  }

  static const int buildNumber = 2;

  final String apiBaseUrl;
  final Duration connectTimeout;
  final Duration sendTimeout;
  final Duration receiveTimeout;
}

final appConfigProvider = Provider<AppConfig>((ref) {
  return AppConfig.fromEnvironment();
});
