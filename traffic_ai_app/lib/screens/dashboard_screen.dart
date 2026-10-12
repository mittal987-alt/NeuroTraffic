// lib/screens/dashboard_screen.dart
//
// Read-only dashboard: pulls summary stats + recent events from the
// FastAPI backend and displays them. No live WebSocket yet -- that's
// Phase 7. This proves the app <-> backend connection works first.

import 'package:flutter/material.dart';
import 'dart:async';
import '../services/api_service.dart';
import '../services/websocket_service.dart';
import 'live_view_screen.dart';
import 'camera_map_screen.dart';
import 'analytics_screen.dart';
import 'alerts_screen.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  final ApiService _api = ApiService();
  final WebSocketService _ws = WebSocketService();
  StreamSubscription? _alertSubscription;

  Map<String, int> _summaryStats = {};
  List<VehicleEvent> _recentEvents = [];
  List<AlertItem> _recentAlerts = [];
  int _activeAlertCount = 0;
  bool _isLoading = true;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    _loadData();
    _setupRealtimeUpdates();
  }

  void _setupRealtimeUpdates() {
    _ws.connect();
    
    // Listen for real-time alerts only for the dashboard dashboard
    _alertSubscription = _ws.alerts.listen((alert) {
      if (mounted) {
        setState(() {
          _activeAlertCount++;
          // Add to recent alerts list if not already there
          if (!_recentAlerts.any((a) => a.id == alert.id)) {
            final newItem = AlertItem(
              id: alert.id,
              alertType: alert.alertType,
              message: alert.message,
              trackId: alert.trackId,
              speedKmh: alert.speedKmh,
              cameraId: alert.cameraId,
              status: alert.status,
              resolutionNotes: null,
              resolvedById: null,
              plateText: alert.plateText,
              timestamp: alert.timestamp,
            );
            _recentAlerts.insert(0, newItem);
            if (_recentAlerts.length > 5) _recentAlerts.removeLast();
          }
        });
        
        // Show a quick notification on the dashboard
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('UNHAPPENING DETECTED: ${alert.message}'),
            backgroundColor: Colors.redAccent,
            duration: const Duration(seconds: 4),
            action: SnackBarAction(
              label: 'VIEW',
              textColor: Colors.white,
              onPressed: () {
                Navigator.of(context).push(
                  MaterialPageRoute(builder: (_) => LiveViewScreen(cameraId: alert.cameraId))
                );
              },
            ),
          ),
        );
      }
    });
  }

  @override
  void dispose() {
    _alertSubscription?.cancel();
    super.dispose();
  }

  Future<void> _loadData() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });
    try {
      // Fetch dashboard data and active alert count in parallel
      final results = await Future.wait([
        _api.fetchSummaryStats(),
        _api.fetchRecentEvents(limit: 30),
        _api.fetchAlerts(status: 'new'),
        _api.fetchRecentAlerts(limit: 5, status: 'new'),
      ]);
      setState(() {
        _summaryStats = results[0] as Map<String, int>;
        _recentEvents = results[1] as List<VehicleEvent>;
        _activeAlertCount = (results[2] as List<AlertItem>).length;
        _recentAlerts = results[3] as List<AlertItem>;
        _isLoading = false;
      });
    } catch (e) {
      setState(() {
        _errorMessage = e.toString();
        _isLoading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('TrafficVision AI'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loadData,
          ),
        ],
      ),
      drawer: Drawer(
        child: SafeArea(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const DrawerHeader(
                decoration: BoxDecoration(color: Colors.blue),
                child: Text('TrafficVision AI', style: TextStyle(color: Colors.white, fontSize: 24)),
              ),
              ListTile(
                leading: const Icon(Icons.bar_chart),
                title: const Text('Analytics'),
                onTap: () {
                  Navigator.of(context).pop();
                  Navigator.of(context).push(MaterialPageRoute(builder: (_) => const AnalyticsScreen()));
                },
              ),
              ListTile(
                leading: const Icon(Icons.videocam),
                title: const Text('Live Feed'),
                onTap: () {
                  Navigator.of(context).pop();
                  Navigator.of(context).push(MaterialPageRoute(builder: (_) => const LiveViewScreen()));
                },
              ),
              ListTile(
                leading: const Icon(Icons.map),
                title: const Text('Camera Map'),
                onTap: () {
                  Navigator.of(context).pop();
                  Navigator.of(context).push(MaterialPageRoute(builder: (_) => const CameraMapScreen()));
                },
              ),
              ListTile(
                leading: const Icon(Icons.warning),
                title: const Text('Alerts'),
                trailing: _activeAlertCount > 0
                    ? CircleAvatar(
                        radius: 12,
                        backgroundColor: Colors.red,
                        child: Text(
                          '$_activeAlertCount',
                          style: const TextStyle(color: Colors.white, fontSize: 12),
                        ),
                      )
                    : null,
                onTap: () async {
                  Navigator.of(context).pop();
                  final didResolve = await Navigator.of(context).push<bool>(
                    MaterialPageRoute(builder: (_) => const AlertsScreen()),
                  );
                  if (mounted && didResolve == true) {
                    _loadData();
                  }
                },
              ),
            ],
          ),
        ),
      ),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_isLoading) {
      return const Center(child: CircularProgressIndicator());
    }

    if (_errorMessage != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24.0),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(Icons.wifi_off, size: 48, color: Colors.grey),
              const SizedBox(height: 16),
              Text(
                'Could not connect to backend:\n$_errorMessage',
                textAlign: TextAlign.center,
                style: const TextStyle(color: Colors.grey),
              ),
              const SizedBox(height: 16),
              ElevatedButton(onPressed: _loadData, child: const Text('Retry')),
            ],
          ),
        ),
      );
    }

    return RefreshIndicator(
      onRefresh: _loadData,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _buildAlertSummaryCard(),
          const SizedBox(height: 16),
          _buildSummaryGrid(),
          const SizedBox(height: 24),
          _buildRecentAlertsSection(),
          const SizedBox(height: 24),
          const Text('Recent Events', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
          const SizedBox(height: 8),
          ..._recentEvents.map(_buildEventTile),
        ],
      ),
    );
  }

  Widget _buildAlertSummaryCard() {
    final hasAlerts = _activeAlertCount > 0;
    return Card(
      color: hasAlerts ? Colors.red.shade50 : Colors.green.shade50,
      elevation: 2,
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Row(
          children: [
            Icon(
              hasAlerts ? Icons.warning_amber_rounded : Icons.check_circle,
              size: 32,
              color: hasAlerts ? Colors.red : Colors.green,
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    hasAlerts ? 'Active Alerts' : 'No active alerts',
                    style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    hasAlerts
                        ? '$_activeAlertCount unresolved alert${_activeAlertCount == 1 ? '' : 's'} needs attention'
                        : 'All alerts are resolved',
                    style: const TextStyle(color: Colors.black54),
                  ),
                ],
              ),
            ),
            if (hasAlerts)
              CircleAvatar(
                radius: 18,
                backgroundColor: Colors.red,
                child: Text(
                  '$_activeAlertCount',
                  style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildRecentAlertsSection() {
    if (_recentAlerts.isEmpty) {
      return const SizedBox.shrink();
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('Recent Alerts', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
        const SizedBox(height: 8),
        ..._recentAlerts.map((alert) {
          return Card(
            elevation: 2,
            margin: const EdgeInsets.only(bottom: 12),
            child: ListTile(
              leading: CircleAvatar(backgroundColor: Colors.red.shade100, child: const Icon(Icons.warning, color: Colors.red)),
              title: Text(alert.message),
              subtitle: RichText(
                text: TextSpan(
                  style: const TextStyle(color: Colors.black54, fontSize: 13),
                  children: [
                    TextSpan(text: '${alert.cameraId} • '),
                    if (alert.plateText != null)
                      TextSpan(
                        text: '[${alert.plateText}] ',
                        style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.blue),
                      )
                    else
                      const TextSpan(text: 'plate unknown • '),
                    TextSpan(text: alert.speedKmh != null ? '${alert.speedKmh!.toStringAsFixed(0)} km/h' : 'speed unknown'),
                  ],
                ),
              ),
              trailing: Chip(
                label: Text(alert.alertType.replaceAll('_', ' ').toUpperCase()),
                backgroundColor: Colors.orange.shade100,
              ),
            ),
          );
        }).toList(),
      ],
    );
  }

  Widget _buildSummaryGrid() {
    return GridView.count(
      crossAxisCount: 2,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      mainAxisSpacing: 12,
      crossAxisSpacing: 12,
      childAspectRatio: 1.6,
      children: _summaryStats.entries.map((entry) {
        return Card(
          elevation: 2,
          child: Padding(
            padding: const EdgeInsets.all(12.0),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text(
                  '${entry.value}',
                  style: const TextStyle(fontSize: 28, fontWeight: FontWeight.bold),
                ),
                Text(entry.key, style: const TextStyle(color: Colors.grey)),
              ],
            ),
          ),
        );
      }).toList(),
    );
  }

  Widget _buildEventTile(VehicleEvent event) {
    return Card(
      child: ListTile(
        leading: CircleAvatar(child: Text(event.vehicleType[0].toUpperCase())),
        title: Text('${event.vehicleType} (ID ${event.trackId})'),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (event.plateText != null)
              Text('Plate: ${event.plateText}', style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.blue)),
            Text(event.timestamp),
          ],
        ),
        trailing: event.speedKmh != null
            ? Text('${event.speedKmh!.toStringAsFixed(0)} km/h')
            : null,
      ),
    );
  }
}