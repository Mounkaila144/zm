import 'package:flutter_test/flutter_test.dart';
import 'package:zarma_mobile/models/recognition_result.dart';

void main() {
  test('mappe strictement tous les champs et préserve les alternatives', () {
    final RecognitionResult result = RecognitionResult.fromLiveJson(
      _response(),
    );

    expect(result.id, 'recognition-id');
    expect(result.recognizedNumber, 100);
    expect(result.zarmaText, 'zangu');
    expect(result.normalizedText, 'zangu');
    expect(result.confidence, 0.98);
    expect(result.decision, Decision.accept);
    expect(result.alternatives.map((item) => item.number), <int?>[90, null]);
    expect(result.modelVersion, 'mock-1');
    expect(result.grammarVersion, 'v1');
    expect(result.latencyTotalMs, 50);
    expect(result.latencyAsrMs, 40);
  });

  test('refuse décision inconnue et accept incohérent', () {
    expect(
      () => RecognitionResult.fromLiveJson(
        _response()..['decision'] = 'unknown',
      ),
      throwsA(isA<RecognitionContractException>()),
    );
    expect(
      () => RecognitionResult.fromLiveJson(
        _response()..['recognized_number'] = null,
      ),
      throwsA(isA<RecognitionContractException>()),
    );
    expect(
      () => RecognitionResult.fromLiveJson(
        _response()..['zarma_text'] = ' ',
      ),
      throwsA(isA<RecognitionContractException>()),
    );
  });

  test('accepte confirm et repeat sans nombre inventé', () {
    for (final String decision in <String>['confirm', 'repeat']) {
      final RecognitionResult result = RecognitionResult.fromLiveJson(
        _response()
          ..['decision'] = decision
          ..['recognized_number'] = null
          ..['zarma_text'] = '',
      );
      expect(result.recognizedNumber, isNull);
      expect(result.decision.name, decision);
    }
  });
}

Map<String, dynamic> _response() {
  return <String, dynamic>{
    'id': 'recognition-id',
    'recognized_number': 100,
    'zarma_text': 'zangu',
    'normalized_text': 'zangu',
    'confidence': 0.98,
    'decision': 'accept',
    'alternatives': <dynamic>[
      <String, dynamic>{
        'number': 90,
        'zarma_text': 'alternative',
        'score': 0.7,
      },
      <String, dynamic>{
        'number': null,
        'zarma_text': '',
        'score': 0.2,
      },
    ],
    'model_version': 'mock-1',
    'grammar_version': 'v1',
    'latency_total_ms': 50,
    'latency_asr_ms': 40,
  };
}
