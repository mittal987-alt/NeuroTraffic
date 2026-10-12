// lib/widgets/mjpeg_view.dart
//
// A minimal MJPEG stream viewer, built directly on the `http` package
// instead of a third-party plugin (avoids version conflicts). Reads
// the multipart/x-mixed-replace stream byte-by-byte, extracts each
// JPEG frame between boundary markers, and displays it as an Image.

import 'dart:async';
import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

class MjpegView extends StatefulWidget {
  final String streamUrl;
  final BoxFit fit;
  final Widget Function(BuildContext context)? errorBuilder;

  const MjpegView({
    super.key,
    required this.streamUrl,
    this.fit = BoxFit.cover,
    this.errorBuilder,
  });

  @override
  State<MjpegView> createState() => _MjpegViewState();
}

class _MjpegViewState extends State<MjpegView> {
  Uint8List? _currentFrame;
  bool _hasError = false;
  http.Client? _client;
  StreamSubscription? _subscription;

  @override
  void initState() {
    super.initState();
    _startStream();
  }

  Future<void> _startStream() async {
    _client = http.Client();
    try {
      final request = http.Request('GET', Uri.parse(widget.streamUrl));
      final response = await _client!.send(request);

      final List<int> buffer = [];
      _subscription = response.stream.listen(
            (chunk) {
          buffer.addAll(chunk);
          _extractFrames(buffer);
        },
        onError: (_) {
          if (mounted) setState(() => _hasError = true);
        },
        onDone: () {
          if (mounted) setState(() => _hasError = true);
        },
      );
    } catch (_) {
      if (mounted) setState(() => _hasError = true);
    }
  }

  void _extractFrames(List<int> buffer) {
    // JPEG frames start with FFD8 and end with FFD9. We scan the
    // buffer for complete frames, emit each one, then discard the
    // consumed bytes so the buffer doesn't grow unbounded.
    while (true) {
      final start = _findBytes(buffer, [0xFF, 0xD8]);
      if (start == -1) return;
      final end = _findBytes(buffer, [0xFF, 0xD9], start + 2);
      if (end == -1) return;

      final frameBytes = Uint8List.fromList(buffer.sublist(start, end + 2));
      buffer.removeRange(0, end + 2);

      if (mounted) {
        setState(() {
          _currentFrame = frameBytes;
          _hasError = false;
        });
      }
    }
  }

  int _findBytes(List<int> buffer, List<int> pattern, [int start = 0]) {
    for (int i = start; i <= buffer.length - pattern.length; i++) {
      bool match = true;
      for (int j = 0; j < pattern.length; j++) {
        if (buffer[i + j] != pattern[j]) {
          match = false;
          break;
        }
      }
      if (match) return i;
    }
    return -1;
  }

  @override
  void dispose() {
    _subscription?.cancel();
    _client?.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_hasError && _currentFrame == null) {
      return widget.errorBuilder?.call(context) ??
          const Center(child: Text('Stream unavailable', style: TextStyle(color: Colors.white70)));
    }
    if (_currentFrame == null) {
      return const Center(child: CircularProgressIndicator());
    }
    return Image.memory(_currentFrame!, fit: widget.fit, gaplessPlayback: true);
  }
}