import 'package:dio/dio.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zarma_mobile/config/app_config.dart';
import 'package:zarma_mobile/network/api_client.dart';

class MobileUpdatePolicy {
  const MobileUpdatePolicy({
    required this.minimumSupportedBuild,
    required this.latestBuild,
    required this.playStoreUrl,
  });

  factory MobileUpdatePolicy.fromJson(Map<String, dynamic> json) {
    final Object? minimum = json['minimum_supported_build'];
    final Object? latest = json['latest_build'];
    final Object? storeUrl = json['play_store_url'];
    if (minimum is! num ||
        latest is! num ||
        minimum < 1 ||
        latest < minimum ||
        storeUrl is! String ||
        storeUrl.trim().isEmpty) {
      throw const FormatException('Invalid mobile update policy');
    }
    return MobileUpdatePolicy(
      minimumSupportedBuild: minimum.toInt(),
      latestBuild: latest.toInt(),
      playStoreUrl: storeUrl,
    );
  }

  final int minimumSupportedBuild;
  final int latestBuild;
  final String playStoreUrl;

  bool get updateRequired => AppConfig.buildNumber < minimumSupportedBuild;
}

class MobileUpdateRepository {
  const MobileUpdateRepository(this._dio);

  final Dio _dio;

  Future<MobileUpdatePolicy> fetch() async {
    final Response<dynamic> response =
        await _dio.get<dynamic>('/mobile/config');
    final Object? data = response.data;
    if (data is! Map<String, dynamic>) {
      throw const FormatException('Invalid mobile update response');
    }
    return MobileUpdatePolicy.fromJson(data);
  }
}

final mobileUpdateRepositoryProvider = Provider<MobileUpdateRepository>((ref) {
  return MobileUpdateRepository(ref.watch(dioProvider));
});

final mobileUpdatePolicyProvider =
    FutureProvider.autoDispose<MobileUpdatePolicy>((ref) {
  return ref.watch(mobileUpdateRepositoryProvider).fetch();
});

abstract interface class ImmediateUpdateGateway {
  Future<bool> start({required String playStoreUrl});
}

class PlayImmediateUpdateGateway implements ImmediateUpdateGateway {
  const PlayImmediateUpdateGateway();

  static const MethodChannel _channel =
      MethodChannel('ne.zarma.zarma_mobile/update');

  @override
  Future<bool> start({required String playStoreUrl}) async {
    try {
      return await _channel.invokeMethod<bool>(
            'startImmediateUpdate',
            <String, dynamic>{'storeUrl': playStoreUrl},
          ) ??
          false;
    } on PlatformException {
      return false;
    } on MissingPluginException {
      return false;
    }
  }
}

final immediateUpdateGatewayProvider = Provider<ImmediateUpdateGateway>((ref) {
  return const PlayImmediateUpdateGateway();
});
