import 'package:flutter_test/flutter_test.dart';
import 'package:tts_recorder/audio_service.dart';

void main() {
  test('la capture master est configurée en WAV 48 kHz mono', () {
    expect(AudioCaptureService.recordingConfig.sampleRate, 48000);
    expect(AudioCaptureService.recordingConfig.numChannels, 1);
    expect(AudioCaptureService.recordingConfig.autoGain, isFalse);
    expect(AudioCaptureService.recordingConfig.echoCancel, isFalse);
    expect(AudioCaptureService.recordingConfig.noiseSuppress, isFalse);
  });
}
