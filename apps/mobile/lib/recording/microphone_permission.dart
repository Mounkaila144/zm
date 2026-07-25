import 'package:permission_handler/permission_handler.dart';

enum MicrophonePermissionStatus {
  granted,
  denied,
  permanentlyDenied,
}

abstract interface class MicrophonePermissionGateway {
  Future<MicrophonePermissionStatus> check();

  Future<MicrophonePermissionStatus> request();

  Future<bool> openSettings();
}

class PermissionHandlerMicrophonePermission
    implements MicrophonePermissionGateway {
  const PermissionHandlerMicrophonePermission();

  @override
  Future<MicrophonePermissionStatus> check() async {
    return microphonePermissionStatusFromPlugin(
      await Permission.microphone.status,
    );
  }

  @override
  Future<MicrophonePermissionStatus> request() async {
    return microphonePermissionStatusFromPlugin(
      await Permission.microphone.request(),
    );
  }

  @override
  Future<bool> openSettings() => openAppSettings();
}

MicrophonePermissionStatus microphonePermissionStatusFromPlugin(
  PermissionStatus status,
) {
  if (status.isGranted) {
    return MicrophonePermissionStatus.granted;
  }
  if (status.isPermanentlyDenied) {
    return MicrophonePermissionStatus.permanentlyDenied;
  }
  return MicrophonePermissionStatus.denied;
}
