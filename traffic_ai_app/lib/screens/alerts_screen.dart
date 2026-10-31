// lib/screens/alerts_screen.dart
//
// Shows active alerts from the backend and lets authenticated users
// resolve them with optional resolution notes.

import 'package:flutter/material.dart';
import 'dart:async';
import '../services/api_service.dart';
import '../services/websocket_service.dart';

class AlertsScreen extends StatefulWidget {
  const AlertsScreen({super.key});

  @override
  State<AlertsScreen> createState() => _AlertsScreenState();
}

class _AlertsScreenState extends State<AlertsScreen> with SingleTickerProviderStateMixin {
  final ApiService _api = ApiService();
  final WebSocketService _ws = WebSocketService();
  StreamSubscription? _alertSubscription;

  late final TabController _tabController;
  List<AlertItem> _activeAlerts = [];
  List<AlertItem> _resolvedAlerts = [];
  bool _isLoading = true;
  bool _didResolveAnyAlert = false;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 2, vsync: this);
    _loadAlerts();
    _setupRealtimeAlerts();
  }

  void _setupRealtimeAlerts() {
    _ws.connect();
    _alertSubscription = _ws.alerts.listen((alert) {
      if (mounted) {
        setState(() {
          // Create a new AlertItem from the WebSocket notification
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
          
          // Add to active alerts if not already in the list
          if (!_activeAlerts.any((a) => a.id == alert.id)) {
            _activeAlerts.insert(0, newItem);
          }
        });
      }
    });
  }

  @override
  void dispose() {
    _alertSubscription?.cancel();
    _tabController.dispose();
    super.dispose();
  }

  Future<bool> _onWillPop() async {
    Navigator.of(context).pop(_didResolveAnyAlert);
    return false;
  }

  Future<void> _loadAlerts() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });
    try {
      final active = await _api.fetchAlerts(status: 'new');
      final resolved = await _api.fetchAlerts(status: 'resolved');
      setState(() {
        _activeAlerts = active;
        _resolvedAlerts = resolved;
        _isLoading = false;
      });
    } catch (e) {
      setState(() {
        _errorMessage = e.toString();
        _isLoading = false;
      });
    }
  }

  Future<void> _resolveAlert(AlertItem alert) async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (context) {
        return AlertDialog(
          title: const Text('Confirm Resolve'),
          content: Text('Are you sure you want to resolve the alert "${alert.alertType}"?'),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text('Cancel'),
            ),
            ElevatedButton(
              onPressed: () => Navigator.of(context).pop(true),
              child: const Text('Continue'),
            ),
          ],
        );
      },
    );

    if (confirm != true) return;

    final notes = await showDialog<String>(
      context: context,
      builder: (context) {
        final controller = TextEditingController();
        return AlertDialog(
          title: const Text('Resolve Alert'),
          content: TextField(
            controller: controller,
            decoration: const InputDecoration(
              labelText: 'Resolution notes',
              hintText: 'Optional notes for this alert',
            ),
            maxLines: 3,
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(null),
              child: const Text('Cancel'),
            ),
            ElevatedButton(
              onPressed: () => Navigator.of(context).pop(controller.text.trim()),
              child: const Text('Resolve'),
            ),
          ],
        );
      },
    );

    if (notes == null) return;

    try {
      await _api.resolveAlert(alert.id, resolutionNotes: notes.isEmpty ? null : notes);
      if (mounted) {
        setState(() {
          _didResolveAnyAlert = true;
        });
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Alert resolved successfully')),
        );
        await _loadAlerts();
        _tabController.index = 1; // switch to Resolved tab after success
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed to resolve alert: $e')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return WillPopScope(
      onWillPop: _onWillPop,
      child: Scaffold(
        appBar: AppBar(
        title: const Text('Alerts'),
        actions: [
          IconButton(
            icon: const Icon(Icons.file_download_outlined),
            tooltip: 'Export Reports',
            onPressed: _showExportDialog,
          ),
          IconButton(
            icon: const Icon(Icons.refresh),
            tooltip: 'Refresh',
            onPressed: _loadAlerts,
          ),
        ],
        bottom: TabBar(
          controller: _tabController,
          tabs: const [
            Tab(text: 'Active'),
            Tab(text: 'Resolved'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabController,
        children: [
          _buildBody(_activeAlerts, showResolveButton: true),
          _buildBody(_resolvedAlerts, showResolveButton: false),
        ],
      ),
    ),
  );
}

  Widget _buildBody(List<AlertItem> alerts, {required bool showResolveButton}) {
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
              const Icon(Icons.error_outline, size: 48, color: Colors.redAccent),
              const SizedBox(height: 16),
              Text('Failed to load alerts:\n$_errorMessage', textAlign: TextAlign.center),
              const SizedBox(height: 16),
              ElevatedButton(onPressed: _loadAlerts, child: const Text('Retry')),
            ],
          ),
        ),
      );
    }
    if (alerts.isEmpty) {
      return Center(
        child: Text(showResolveButton ? 'No active alerts at the moment.' : 'No resolved alerts yet.'),
      );
    }
    return ListView.separated(
      padding: const EdgeInsets.all(16),
      itemCount: alerts.length,
      separatorBuilder: (_, __) => const SizedBox(height: 12),
      itemBuilder: (context, index) {
        final alert = alerts[index];
        return Card(
          elevation: 2,
          child: Padding(
            padding: const EdgeInsets.all(12.0),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Expanded(
                      child: Text(
                        alert.alertType.replaceAll('_', ' ').toUpperCase(),
                        style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                      ),
                    ),
                    Chip(
                      label: Text(alert.status.toUpperCase()),
                      backgroundColor: alert.status == 'resolved' ? Colors.green.shade100 : Colors.orange.shade100,
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Text(alert.message),
                const SizedBox(height: 8),
                Row(
                  children: [
                    Text('Camera: ${alert.cameraId} • ID ${alert.trackId ?? 'N/A'}', style: const TextStyle(color: Colors.grey)),
                    if (alert.plateText != null) ...[
                      const SizedBox(width: 12),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                        decoration: BoxDecoration(
                          color: Colors.blue.shade50,
                          borderRadius: BorderRadius.circular(4),
                          border: Border.all(color: Colors.blue.shade200),
                        ),
                        child: Text(
                          alert.plateText!,
                          style: TextStyle(
                            color: Colors.blue.shade800,
                            fontWeight: FontWeight.bold,
                            fontSize: 11,
                            letterSpacing: 0.5,
                          ),
                        ),
                      ),
                    ],
                  ],
                ),
                const SizedBox(height: 4),
                Text('Time: ${alert.timestamp}', style: const TextStyle(color: Colors.grey)),
                if (alert.speedKmh != null) ...[
                  const SizedBox(height: 8),
                  Text('Speed: ${alert.speedKmh!.toStringAsFixed(0)} km/h'),
                ],
                if (alert.resolutionNotes != null && alert.resolutionNotes!.isNotEmpty) ...[
                  const SizedBox(height: 8),
                  Text('Notes: ${alert.resolutionNotes}', style: const TextStyle(color: Colors.black87)),
                ],
                if (!showResolveButton) ...[
                  const SizedBox(height: 8),
                  Text('Resolved by: ${alert.resolvedById ?? 'unknown'}', style: const TextStyle(color: Colors.grey)),
                ],
                const SizedBox(height: 12),
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    OutlinedButton.icon(
                      icon: const Icon(Icons.picture_as_pdf, size: 16, color: Colors.indigo),
                      label: const Text('E-Challan', style: TextStyle(color: Colors.indigo, fontSize: 13)),
                      style: OutlinedButton.styleFrom(
                        side: BorderSide(color: Colors.indigo.shade200),
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                      ),
                      onPressed: () => _handleChallanAction(alert),
                    ),
                    if (showResolveButton)
                      ElevatedButton(
                        onPressed: () => _resolveAlert(alert),
                        child: const Text('Resolve'),
                      ),
                  ],
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Future<void> _handleChallanAction(AlertItem alert) async {
    if (alert.status == 'new') {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Alert must be reviewed before an e-challan can be issued.'),
          backgroundColor: Colors.orange,
        ),
      );
      return;
    }

    try {
      if (alert.status == 'reviewed') {
        await _api.issueChallan(alert.id);
        _loadAlerts();
      }
      final challanUrl = await _api.getAuthenticatedChallanUrl(alert.id);
      if (mounted) {
        _showChallanDialog(alert, challanUrl);
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Failed to process challan: $e'),
            backgroundColor: Colors.red,
          ),
        );
      }
    }
  }

  void _showChallanDialog(AlertItem alert, String challanUrl) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: Row(
          children: [
            const Icon(Icons.receipt_long, color: Colors.indigo),
            const SizedBox(width: 8),
            const Text('E-Challan Notice', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Notice ID: TRF-CH-${alert.id.toString().padLeft(5, '0')}', style: const TextStyle(fontWeight: FontWeight.bold)),
            const SizedBox(height: 6),
            Text('Offense: ${alert.alertType.replaceAll('_', ' ').toUpperCase()}'),
            Text('Plate: ${alert.plateText ?? 'Unregistered / Not Captured'}'),
            if (alert.speedKmh != null) Text('Recorded Speed: ${alert.speedKmh!.toStringAsFixed(1)} km/h'),
            Text('Camera: ${alert.cameraId}'),
            Text('Timestamp: ${alert.timestamp}'),
            const Divider(height: 20),
            Text('Download URL:\n$challanUrl', style: const TextStyle(fontSize: 11, color: Colors.grey)),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Close'),
          ),
          ElevatedButton.icon(
            icon: const Icon(Icons.download, size: 16),
            label: const Text('Download PDF'),
            onPressed: () {
              Navigator.pop(context);
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(
                  content: Text('E-Challan ready: $challanUrl'),
                  duration: const Duration(seconds: 4),
                ),
              );
            },
          ),
        ],
      ),
    );
  }

  void _showExportDialog() {
    final alertsCsvUrl = _api.getExportAlertsCsvUrl();
    final eventsCsvUrl = _api.getExportEventsCsvUrl();
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: Row(
          children: [
            const Icon(Icons.table_chart, color: Colors.teal),
            const SizedBox(width: 8),
            const Text('Export Traffic Reports', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Download audit spreadsheets in CSV format:'),
            const SizedBox(height: 12),
            ListTile(
              dense: true,
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.warning_amber, color: Colors.orange),
              title: const Text('Violations & Alerts (CSV)', style: TextStyle(fontWeight: FontWeight.bold)),
              subtitle: Text(alertsCsvUrl, style: const TextStyle(fontSize: 10, color: Colors.grey)),
            ),
            const SizedBox(height: 8),
            ListTile(
              dense: true,
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.directions_car, color: Colors.blue),
              title: const Text('Vehicle Counting & Flow (CSV)', style: TextStyle(fontWeight: FontWeight.bold)),
              subtitle: Text(eventsCsvUrl, style: const TextStyle(fontSize: 10, color: Colors.grey)),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Close'),
          ),
          ElevatedButton.icon(
            icon: const Icon(Icons.file_download, size: 16),
            label: const Text('Export Alerts CSV'),
            onPressed: () {
              Navigator.pop(context);
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(content: Text('Export link: $alertsCsvUrl')),
              );
            },
          ),
        ],
      ),
    );
  }
}
