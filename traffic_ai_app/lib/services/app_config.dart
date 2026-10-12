// lib/services/app_config.dart
import 'package:flutter/foundation.dart';

class AppConfig {
  static const int port = 8000;

  // 1. You can pass custom IP via --dart-define=SERVER_IP=192.168.1.X
  static const String _envServerIp = String.fromEnvironment('SERVER_IP', defaultValue: '');

  // 2. Default fallback IP (change this to your Wi-Fi IP if running on a physical phone)
  static String customIp = "10.135.201.5";

  static String get serverIp {
    if (_envServerIp.isNotEmpty) {
      return _envServerIp;
    }
    if (kIsWeb) {
      return "127.0.0.1";
    }
    if (defaultTargetPlatform == TargetPlatform.windows ||
        defaultTargetPlatform == TargetPlatform.macOS ||
        defaultTargetPlatform == TargetPlatform.linux) {
      return "127.0.0.1";
    }
    // On Android / iOS physical device or emulator
    return customIp;
  }

  static String get baseUrl => "http://$serverIp:$port";
  static String get wsUrl => "ws://$serverIp:$port/ws/live";
}
