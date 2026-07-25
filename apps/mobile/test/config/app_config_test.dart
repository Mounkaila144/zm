import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:zarma_mobile/config/app_config.dart';

void main() {
  test('la configuration API est surchargeable via Riverpod', () {
    const AppConfig overriddenConfig = AppConfig(
      apiBaseUrl: 'http://192.0.2.1:9000/api/v1',
    );
    final ProviderContainer container = ProviderContainer(
      overrides: <Override>[
        appConfigProvider.overrideWithValue(overriddenConfig),
      ],
    );
    addTearDown(container.dispose);

    expect(container.read(appConfigProvider), same(overriddenConfig));
    expect(container.read(appConfigProvider).apiBaseUrl,
        overriddenConfig.apiBaseUrl);
  });

  test('la configuration par défaut ne contient aucun secret', () {
    final AppConfig config = AppConfig.fromEnvironment();

    expect(config.apiBaseUrl, startsWith('http://'));
    expect(config.apiBaseUrl, isNot(contains('token')));
    expect(config.apiBaseUrl, isNot(contains('secret')));
    expect(config.apiBaseUrl, isNot(contains('@')));
  });
}
