import 'dart:async';

abstract interface class RecordingTicker {
  Stream<Duration> get ticks;

  Future<void> dispose();
}

class PeriodicRecordingTicker implements RecordingTicker {
  PeriodicRecordingTicker({
    this.interval = const Duration(milliseconds: 200),
  }) {
    _controller = StreamController<Duration>(
      onListen: _start,
      onCancel: () {
        _timer?.cancel();
        _timer = null;
        _stopwatch.stop();
      },
    );
  }

  final Duration interval;
  late final StreamController<Duration> _controller;
  final Stopwatch _stopwatch = Stopwatch();
  Timer? _timer;

  @override
  Stream<Duration> get ticks => _controller.stream;

  void _start() {
    _stopwatch.start();
    _timer = Timer.periodic(interval, (_) {
      if (!_controller.isClosed) {
        _controller.add(_stopwatch.elapsed);
      }
    });
  }

  @override
  Future<void> dispose() async {
    _timer?.cancel();
    _timer = null;
    _stopwatch.stop();
    if (!_controller.isClosed) {
      await _controller.close();
    }
  }
}
