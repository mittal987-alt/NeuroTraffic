// lib/services/auth_service.dart

import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'app_config.dart';

class AuthService {
  static String get baseUrl => AppConfig.baseUrl;

  final _storage = const FlutterSecureStorage();

  /// Extracts a readable error message from a failed response,
  /// without crashing if the body isn't JSON or `detail` isn't a
  /// plain string (e.g. FastAPI validation errors return a list).
  String _extractErrorMessage(http.Response response) {
    try {
      final decoded = jsonDecode(response.body);
      final detail = decoded is Map ? decoded['detail'] : null;
      if (detail is String) return detail;
      if (detail is List && detail.isNotEmpty) {
        // FastAPI validation error format: list of {msg, loc, ...}
        final first = detail.first;
        if (first is Map && first['msg'] != null) {
          return first['msg'].toString();
        }
        return detail.toString();
      }
      return 'Request failed (${response.statusCode})';
    } catch (_) {
      return 'Request failed (${response.statusCode}): ${response.body}';
    }
  }

  Future<Map<String, dynamic>> signup(
      String email,
      String name,
      String password,
      ) async {
    late http.Response response;

    try {
      response = await http.post(
        Uri.parse('$baseUrl/auth/signup'),
        headers: {
          'Content-Type': 'application/json',
        },
        body: jsonEncode({
          'email': email,
          'name': name,
          'password': password,
        }),
      ).timeout(const Duration(seconds: 10));

      debugPrint('SIGNUP URL: $baseUrl/auth/signup');
      debugPrint('SIGNUP STATUS: ${response.statusCode}');
      debugPrint('SIGNUP RESPONSE: ${response.body}');
    } catch (e) {
      throw Exception(
        'Could not reach the server at $baseUrl. '
            'Make sure the backend is running and your device is on the same network. ($e)',
      );
    }

    if (response.statusCode == 200 || response.statusCode == 201) {
      final data = jsonDecode(response.body);

      await _storage.write(
        key: 'access_token',
        value: data['access_token'],
      );

      return data;
    }

    throw Exception(_extractErrorMessage(response));
  }

  Future<Map<String, dynamic>> login(String email, String password) async {
    late http.Response response;
    try {
      response = await http.post(
        Uri.parse('$baseUrl/auth/login'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'email': email, 'password': password}),
      ).timeout(const Duration(seconds: 10));
    } catch (e) {
      throw Exception(
        'Could not reach the server at $baseUrl. Make sure the backend '
            'is running and your device is on the same network. ($e)',
      );
    }

    if (response.statusCode == 200) {
      final data = jsonDecode(response.body);
      await _storage.write(key: 'access_token', value: data['access_token']);
      return data;
    }
    throw Exception(_extractErrorMessage(response));
  }

  Future<String?> getToken() async {
    return await _storage.read(key: 'access_token');
  }

  Future<bool> isLoggedIn() async {
    final token = await getToken();
    if (token == null) return false;
    // Verify the token is still valid by calling /auth/me
    try {
      final response = await http
          .get(
        Uri.parse('$baseUrl/auth/me'),
        headers: {'Authorization': 'Bearer $token'},
      )
          .timeout(const Duration(seconds: 10));
      return response.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  Future<void> logout() async {
    await _storage.delete(key: 'access_token');
  }
}
