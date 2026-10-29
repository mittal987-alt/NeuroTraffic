// lib/services/websocket_service.dart
//
// Connects to the FastAPI /ws/live endpoint and exposes incoming
// detection frames as a Dart Stream that widgets can listen to.

import 'dart:async';
import 'dart:convert';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'app_config.dart';
import 'auth_service.dart';

class LiveFrame {
  final String cameraId;
  final int frameNumber;
  final List<LiveVehicle> vehicles;
  final Map<String, int> counts;
  final DensityInfo? density;
  final String? signalState;
  final bool isGreenCorridor;

  LiveFrame({
    required this.cameraId,
    required this.frameNumber,
    required this.vehicles,
    required this.counts,
    this.density,
    this.signalState,
    this.isGreenCorridor = false,
  });

  factory LiveFrame.fromJson(Map<String, dynamic> json) {
    return LiveFrame(
      cameraId: json['camera_id'] ?? 'camera_1',
      frameNumber: json['frame'],
      vehicles: (json['vehicles'] as List).map((v) => LiveVehicle.fromJson(v)).toList(),
      counts: Map<String, int>.from(json['counts']),
      density: json['density'] != null ? DensityInfo.fromJson(json['density']) : null,
      signalState: json['signal_state'],
      isGreenCorridor: json['is_green_corridor'] ?? false,
    );
  }
}

class LiveVehicle {
  final int id;
  final String type;
  final double? speedKmh;
  final String? plateText;

  LiveVehicle({required this.id, required this.type, required this.speedKmh, this.plateText});

  factory LiveVehicle.fromJson(Map<String, dynamic> json) {
    return LiveVehicle(
      id: json['id'],
      type: json['type'],
      speedKmh: json['speed_kmh'] != null ? (json['speed_kmh'] as num).toDouble() : null,
      plateText: json['plate_text'],
    );
  }
}

class DensityInfo {
  final String level;
  final String color;
  final int count;

  DensityInfo({required this.level, required this.color, required this.count});

  factory DensityInfo.fromJson(Map<String, dynamic> json) {
    return DensityInfo(level: json['level'], color: json['color'], count: json['count']);
  }
}

class AlertNotification {
  final int id;
  final String alertType;
  final String message;
  final int? trackId;
  final double? speedKmh;
  final String cameraId;
  final String status;
  final String? plateText;
  final String timestamp;

  AlertNotification({
    required this.id,
    required this.alertType,
    required this.message,
    required this.trackId,
    required this.speedKmh,
    required this.cameraId,
    required this.status,
    required this.plateText,
    required this.timestamp,
  });

  factory AlertNotification.fromJson(Map<String, dynamic> json) {
    return AlertNotification(
      id: json['id'],
      alertType: json['alert_type'],
      message: json['message'],
      trackId: json['track_id'],
      speedKmh: json['speed_kmh'] != null ? (json['speed_kmh'] as num).toDouble() : null,
      cameraId: json['camera_id'],
      status: json['status'] ?? 'new',
      plateText: json['plate_text'],
      timestamp: json['timestamp'],
    );
  }
}

class WebSocketService {
  static String get wsUrl => AppConfig.wsUrl;
  final _authService = AuthService();

  WebSocketChannel? _channel;
  final _controller = StreamController<LiveFrame>.broadcast();
  final _alertController = StreamController<AlertNotification>.broadcast();

  Stream<LiveFrame> get frames => _controller.stream;
  Stream<AlertNotification> get alerts => _alertController.stream;
  bool get isConnected => _channel != null;

  Future<void> connect() async {
    if (_channel != null) return;
    final token = await _authService.getToken();
    final effectiveWsUrl = token != null ? '$wsUrl?token=$token' : wsUrl;
    _channel = WebSocketChannel.connect(Uri.parse(effectiveWsUrl));

    _channel!.stream.listen(
      (message) {
        final data = jsonDecode(message);
        if (data is Map<String, dynamic> && data['type'] == 'alert') {
          _alertController.add(AlertNotification.fromJson(data));
        } else {
          _controller.add(LiveFrame.fromJson(data));
        }
      },
      onError: (error) {
        _controller.addError(error);
        disconnect();
      },
      onDone: () {
        disconnect();
      },
    );
  }

  void disconnect() {
    _channel?.sink.close();
    _channel = null;
  }

  void dispose() {
    disconnect();
    _controller.close();
    _alertController.close();
  }
}