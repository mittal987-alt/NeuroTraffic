// lib/services/api_service.dart
//
// Handles all HTTP calls to the FastAPI backend.
//
// IMPORTANT - base URL depends on where you're running the app:
//   - Android emulator: 10.0.2.2 (special alias for your PC's localhost)
//   - iOS simulator: 127.0.0.1 works directly
//   - Physical phone: use your PC's actual LAN IP, e.g. 192.168.1.42
//     (find it with `ipconfig` on Windows, must be on the same WiFi network)

import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import 'auth_service.dart';
import 'app_config.dart';

class VehicleEvent {
  final int id;
  final int trackId;
  final String vehicleType;
  final double? speedKmh;
  final String cameraId;
  final String? plateText;
  final String timestamp;

  VehicleEvent({
    required this.id,
    required this.trackId,
    required this.vehicleType,
    required this.speedKmh,
    required this.cameraId,
    this.plateText,
    required this.timestamp,
  });

  factory VehicleEvent.fromJson(Map<String, dynamic> json) {
    return VehicleEvent(
      id: json['id'],
      trackId: json['track_id'],
      vehicleType: json['vehicle_type'],
      speedKmh: json['speed_kmh'] != null ? (json['speed_kmh'] as num).toDouble() : null,
      cameraId: json['camera_id'],
      plateText: json['plate_text'],
      timestamp: json['timestamp'],
    );
  }
}

class TrafficCamera {
  final String id;
  final String name;
  final double latitude;
  final double longitude;
  final String status;
  final String lastSeen;

  TrafficCamera({
    required this.id,
    required this.name,
    required this.latitude,
    required this.longitude,
    required this.status,
    required this.lastSeen,
  });

  factory TrafficCamera.fromJson(Map<String, dynamic> json) {
    return TrafficCamera(
      id: json['id'],
      name: json['name'],
      latitude: (json['latitude'] as num).toDouble(),
      longitude: (json['longitude'] as num).toDouble(),
      status: json['status'],
      lastSeen: json['last_seen'],
    );
  }
}

class AlertItem {
  final int id;
  final String alertType;
  final String message;
  final int? trackId;
  final double? speedKmh;
  final String cameraId;
  final String status;
  final String? resolutionNotes;
  final int? resolvedById;
  final String? plateText;
  final String timestamp;

  AlertItem({
    required this.id,
    required this.alertType,
    required this.message,
    required this.trackId,
    required this.speedKmh,
    required this.cameraId,
    required this.status,
    required this.resolutionNotes,
    required this.resolvedById,
    required this.plateText,
    required this.timestamp,
  });

  factory AlertItem.fromJson(Map<String, dynamic> json) {
    return AlertItem(
      id: json['id'],
      alertType: json['alert_type'],
      message: json['message'],
      trackId: json['track_id'],
      speedKmh: json['speed_kmh'] != null ? (json['speed_kmh'] as num).toDouble() : null,
      cameraId: json['camera_id'],
      status: json['status'],
      resolutionNotes: json['resolution_notes'],
      resolvedById: json['resolved_by_id'],
      plateText: json['plate_text'],
      timestamp: json['timestamp'],
    );
  }
}

class ApiService {
  static String get baseUrl => AppConfig.baseUrl;
  final _authService = AuthService();

  Future<Map<String, String>> _authHeaders() async {
    final token = await _authService.getToken();
    return token != null
        ? {'Content-Type': 'application/json', 'Authorization': 'Bearer $token'}
        : {'Content-Type': 'application/json'};
  }

  Future<List<VehicleEvent>> fetchRecentEvents({int limit = 50}) async {
    final response = await http.get(Uri.parse('$baseUrl/events?limit=$limit'));

    if (response.statusCode == 200) {
      final List<dynamic> data = jsonDecode(response.body);
      return data.map((json) => VehicleEvent.fromJson(json)).toList();
    } else {
      throw Exception('Failed to load events (status ${response.statusCode})');
    }
  }

  Future<List<Map<String, dynamic>>> fetchHourlyTraffic({int hoursBack = 24}) async {
    final response = await http.get(Uri.parse('$baseUrl/analytics/hourly?hours_back=$hoursBack'));
    if (response.statusCode == 200) {
      return List<Map<String, dynamic>>.from(jsonDecode(response.body));
    }
    throw Exception('Failed to load hourly traffic (status ${response.statusCode})');
  }

  Future<List<Map<String, dynamic>>> fetchAlertBreakdown() async {
    final response = await http.get(Uri.parse('$baseUrl/analytics/alerts'));
    if (response.statusCode == 200) {
      return List<Map<String, dynamic>>.from(jsonDecode(response.body));
    }
    throw Exception('Failed to load alert breakdown (status ${response.statusCode})');
  }

  Future<List<TrafficCamera>> fetchCameras() async {
    final response = await http.get(Uri.parse('$baseUrl/cameras'));
    if (response.statusCode == 200) {
      final List<dynamic> data = jsonDecode(response.body);
      return data.map((json) => TrafficCamera.fromJson(json)).toList();
    }
    throw Exception('Failed to load cameras (status ${response.statusCode})');
  }

  Future<List<Map<String, dynamic>>> fetchVehicleTypeBreakdown() async {
    final response = await http.get(Uri.parse('$baseUrl/analytics/vehicle_types'));
    if (response.statusCode == 200) {
      return List<Map<String, dynamic>>.from(jsonDecode(response.body));
    }
    throw Exception('Failed to load vehicle type breakdown (status ${response.statusCode})');
  }

  Future<List<AlertItem>> fetchAlerts({int limit = 50, String? status}) async {
    final query = status != null ? '?limit=$limit&status=$status' : '?limit=$limit';
    final headers = await _authHeaders();
    final response = await http.get(Uri.parse('$baseUrl/alerts$query'), headers: headers);
    if (response.statusCode == 200) {
      final List<dynamic> data = jsonDecode(response.body);
      return data.map((json) => AlertItem.fromJson(json as Map<String, dynamic>)).toList();
    }
    throw Exception('Failed to load alerts (status ${response.statusCode})');
  }

  Future<void> resolveAlert(int alertId, {String? resolutionNotes}) async {
    final headers = await _authHeaders();
    final response = await http.post(
      Uri.parse('$baseUrl/alerts/$alertId/resolve'),
      headers: headers,
      body: jsonEncode({'resolution_notes': resolutionNotes}),
    );
    if (response.statusCode != 200) {
      throw Exception('Failed to resolve alert (status ${response.statusCode})');
    }
  }

  Future<List<AlertItem>> fetchRecentAlerts({int limit = 5, String? status}) async {
    final query = status != null ? '?limit=$limit&status=$status' : '?limit=$limit';
    final headers = await _authHeaders();
    final response = await http.get(Uri.parse('$baseUrl/alerts$query'), headers: headers);
    if (response.statusCode == 200) {
      final List<dynamic> data = jsonDecode(response.body);
      return data.map((json) => AlertItem.fromJson(json as Map<String, dynamic>)).toList();
    }
    throw Exception('Failed to load recent alerts (status ${response.statusCode})');
  }

  Future<Map<String, int>> fetchSummaryStats() async {
    final response = await http.get(Uri.parse('$baseUrl/stats/summary'));

    if (response.statusCode == 200) {
      final Map<String, dynamic> data = jsonDecode(response.body);
      return data.map((key, value) => MapEntry(key, value as int));
    } else {
      throw Exception('Failed to load stats (status ${response.statusCode})');
    }
  }

  String getChallanUrl(int alertId) => '$baseUrl/alerts/$alertId/challan';
  String getExportAlertsCsvUrl({String? status}) =>
      status != null ? '$baseUrl/export/alerts.csv?status=$status' : '$baseUrl/export/alerts.csv';
  String getExportEventsCsvUrl() => '$baseUrl/export/events.csv';

  Future<Map<String, dynamic>> triggerGreenCorridor(String cameraId, {int durationSec = 25}) async {
    final response = await http.post(
      Uri.parse('$baseUrl/signals/$cameraId/green_corridor?duration_sec=$durationSec'),
    );
    if (response.statusCode == 200) {
      return jsonDecode(response.body);
    }
    throw Exception('Failed to activate Green Corridor (status ${response.statusCode})');
  }
}
