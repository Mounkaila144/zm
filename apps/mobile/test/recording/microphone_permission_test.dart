import 'package:flutter_test/flutter_test.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:zarma_mobile/recording/microphone_permission.dart';

void main() {
  test('distingue accord, refus et refus permanent', () {
    expect(
      microphonePermissionStatusFromPlugin(PermissionStatus.granted),
      MicrophonePermissionStatus.granted,
    );
    expect(
      microphonePermissionStatusFromPlugin(PermissionStatus.denied),
      MicrophonePermissionStatus.denied,
    );
    expect(
      microphonePermissionStatusFromPlugin(PermissionStatus.permanentlyDenied),
      MicrophonePermissionStatus.permanentlyDenied,
    );
  });
}
