// lib/screens/live_view_screen.dart
//
// Real-time view: shows the actual live video feed (MJPEG stream)
// with detection overlays already drawn server-side, plus live
// counts, density, signal state, and a scrolling vehicle list --
// all driven by the WebSocket stream.

import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import '../widgets/mjpeg_view.dart';
import '../services/websocket_service.dart';
import '../services/api_service.dart';

class LiveViewScreen extends StatefulWidget {
  final String cameraId;
  const LiveViewScreen({super.key, this.cameraId = 'camera_1'});

  @override
  State<LiveViewScreen> createState() => _LiveViewScreenState();
}

class _LiveViewScreenState extends State<LiveViewScreen> {
  final WebSocketService _ws = WebSocketService();
  final ApiService _api = ApiService();
  LiveFrame? _latestFrame;
  final List<AlertNotification> _alertHistory = [];
  StreamSubscription<AlertNotification>? _alertSubscription;
  String? _errorMessage;
  bool _isTriggeringCorridor = false;

  String get _videoStreamUrl => "${ApiService.baseUrl}/stream/${widget.cameraId}";

  @override
  void initState() {
    super.initState();
    _ws.connect();
    _ws.frames.listen(
      (frame) {
        if (mounted) setState(() => _latestFrame = frame);
      },
      onError: (error) {
        if (mounted) setState(() => _errorMessage = error.toString());
      },
    );
    _alertSubscription = _ws.alerts.listen((alert) {
      if (mounted) {
        // If we are looking at a specific camera, we might want to only show its alerts,
        // OR show all alerts but label them. Here we show all and label them.
        setState(() {
          _alertHistory.insert(0, alert);
          if (_alertHistory.length > 20) _alertHistory.removeLast();
        });
        
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Row(
              children: [
                const Icon(Icons.warning_rounded, color: Colors.white),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    '[${alert.cameraId}] ${alert.alertType.replaceAll('_', ' ').toUpperCase()}: ${alert.message}',
                    style: const TextStyle(fontWeight: FontWeight.bold),
                  ),
                ),
              ],
            ),
            duration: const Duration(seconds: 4),
            backgroundColor: Colors.red.shade700,
            action: alert.cameraId != widget.cameraId ? SnackBarAction(
              label: 'VIEW',
              textColor: Colors.white,
              onPressed: () {
                Navigator.of(context).pushReplacement(
                  MaterialPageRoute(builder: (_) => LiveViewScreen(cameraId: alert.cameraId))
                );
              },
            ) : null,
          ),
        );
      }
    });
  }

  Future<void> _triggerGreenCorridor() async {
    setState(() => _isTriggeringCorridor = true);
    try {
      await _api.triggerGreenCorridor(widget.cameraId, durationSec: 25);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            backgroundColor: Colors.green.shade700,
            content: Row(
              children: [
                const Icon(Icons.emergency, color: Colors.white),
                const SizedBox(width: 8),
                Expanded(
                  child: Text('Green Corridor activated for ${widget.cameraId.toUpperCase()} (25s)'),
                ),
              ],
            ),
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed to trigger Green Corridor: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => _isTriggeringCorridor = false);
    }
  }

  @override
  void dispose() {
    _alertSubscription?.cancel();
    _ws.disconnect(); // Correctly disconnect WebSocket
    super.dispose();
  }

  Color _densityColor(String? colorName) {
    switch (colorName) {
      case 'green':
        return Colors.green;
      case 'yellow':
        return Colors.amber;
      case 'orange':
        return Colors.orange;
      case 'red':
        return Colors.red;
      default:
        return Colors.grey;
    }
  }

  Color _vehicleTypeColor(String type) {
    switch (type) {
      case 'car':
        return Colors.blue;
      case 'motorcycle':
        return Colors.purple;
      case 'bus':
        return Colors.orange;
      case 'truck':
        return Colors.brown;
      default:
        return Colors.grey;
    }
  }

  IconData _vehicleTypeIcon(String type) {
    switch (type) {
      case 'car':
        return Icons.directions_car;
      case 'motorcycle':
        return Icons.two_wheeler;
      case 'bus':
        return Icons.directions_bus;
      case 'truck':
        return Icons.local_shipping;
      default:
        return Icons.directions_car;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF5F6FA),
      appBar: AppBar(
        title: const Text('Live Feed'),
        elevation: 0,
      ),
      body: _errorMessage != null
          ? _buildErrorState()
          : _latestFrame == null
          ? const Center(child: CircularProgressIndicator())
          : _buildLiveContent(_latestFrame!),
    );
  }

  Widget _buildErrorState() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24.0),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.wifi_off, size: 48, color: Colors.grey),
            const SizedBox(height: 16),
            Text('Connection error:\n$_errorMessage', textAlign: TextAlign.center, style: const TextStyle(color: Colors.grey)),
            const SizedBox(height: 16),
            ElevatedButton(
              onPressed: () {
                setState(() {
                  _errorMessage = null;
                  _ws.connect();
                });
              },
              child: const Text('Retry'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildLiveContent(LiveFrame frame) {
    return ListView(
      padding: const EdgeInsets.all(12),
      children: [
        // --- Recent "Unhappenings" (Alerts) Section ---
        if (_alertHistory.isNotEmpty) ...[
          const Padding(
            padding: EdgeInsets.only(left: 4, bottom: 8),
            child: Text('Recent Alerts', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: Colors.red)),
          ),
          ..._alertHistory.map(_buildAlertCard),
          const SizedBox(height: 16),
        ],

        // --- Live video preview ---
        ClipRRect(
          borderRadius: BorderRadius.circular(16),
          child: AspectRatio(
            aspectRatio: 16 / 9,
            child: Stack(
              fit: StackFit.expand,
              children: [
                MjpegView(
                  streamUrl: _videoStreamUrl,
                  fit: BoxFit.cover,
                  errorBuilder: (context) => Container(
                    color: Colors.black87,
                    child: const Center(
                      child: Text('Video stream unavailable', style: TextStyle(color: Colors.white70)),
                    ),
                  ),
                ),
                if (frame.isGreenCorridor)
                  Positioned(
                    top: 0,
                    left: 0,
                    right: 0,
                    child: Container(
                      padding: const EdgeInsets.symmetric(vertical: 4, horizontal: 8),
                      color: Colors.red.shade900.withOpacity(0.9),
                      child: const Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(Icons.emergency, color: Colors.amberAccent, size: 16),
                          SizedBox(width: 6),
                          Text(
                            'EMERGENCY GREEN CORRIDOR ACTIVE',
                            style: TextStyle(
                              color: Colors.white,
                              fontSize: 11,
                              fontWeight: FontWeight.bold,
                              letterSpacing: 0.8,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                Positioned(
                  top: frame.isGreenCorridor ? 32 : 10,
                  left: 10,
                  child: _liveBadge(),
                ),
                if (frame.signalState != null)
                  Positioned(
                    top: frame.isGreenCorridor ? 32 : 10,
                    right: 10,
                    child: _signalBadge(frame.isGreenCorridor ? 'green' : frame.signalState!),
                  ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 16),

        // --- Density + frame info row ---
        if (frame.density != null) _buildDensityCard(frame.density!),
        const SizedBox(height: 16),

        // --- Vehicle count grid ---
        _buildCountGrid(frame.counts),
        const SizedBox(height: 20),

        // --- Vehicle list header ---
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 4),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text('Vehicles in view', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
              Text('Frame ${frame.frameNumber}', style: const TextStyle(color: Colors.grey, fontSize: 12)),
            ],
          ),
        ),
        const SizedBox(height: 8),

        if (frame.vehicles.isEmpty)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 24),
            child: Center(child: Text('No vehicles currently visible', style: TextStyle(color: Colors.grey))),
          )
        else
          ...frame.vehicles.map(_buildVehicleTile),
      ],
    );
  }

  Widget _buildAlertCard(AlertNotification alert) {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.red.shade900,
        borderRadius: BorderRadius.circular(12),
        boxShadow: [BoxShadow(color: Colors.black.withOpacity(0.1), blurRadius: 4, offset: const Offset(0, 2))],
      ),
      child: Row(
        children: [
          const Icon(Icons.warning_amber_rounded, color: Colors.white, size: 28),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Text(
                      alert.alertType.replaceAll('_', ' ').toUpperCase(),
                      style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 14),
                    ),
                    if (alert.plateText != null) ...[
                      const SizedBox(width: 8),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                        decoration: BoxDecoration(
                          color: Colors.white.withOpacity(0.2),
                          borderRadius: BorderRadius.circular(4),
                        ),
                        child: Text(
                          alert.plateText!,
                          style: const TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.bold, letterSpacing: 1),
                        ),
                      ),
                    ],
                  ],
                ),
                const SizedBox(height: 2),
                Text(
                  alert.message,
                  style: const TextStyle(color: Colors.white70, fontSize: 12),
                ),
              ],
            ),
          ),
          Text(
            alert.timestamp.length >= 19 ? alert.timestamp.substring(11, 16) : '',
            style: const TextStyle(color: Colors.white54, fontSize: 10),
          ),
        ],
      ),
    );
  }

  Widget _liveBadge() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: Colors.red,
        borderRadius: BorderRadius.circular(20),
      ),
      child: const Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.circle, size: 8, color: Colors.white),
          SizedBox(width: 6),
          Text('LIVE', style: TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.bold)),
        ],
      ),
    );
  }

  Widget _signalBadge(String state) {
    final isRed = state == 'red';
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: Colors.black54,
        borderRadius: BorderRadius.circular(20),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.circle, size: 10, color: isRed ? Colors.red : Colors.green),
          const SizedBox(width: 6),
          Text(state.toUpperCase(), style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.bold)),
        ],
      ),
    );
  }

  Widget _buildDensityCard(DensityInfo density) {
    final color = _densityColor(density.color);
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: color.withOpacity(0.12),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: color.withOpacity(0.3)),
      ),
      child: Row(
        children: [
          Container(
            width: 12,
            height: 12,
            decoration: BoxDecoration(color: color, shape: BoxShape.circle),
          ),
          const SizedBox(width: 10),
          Text(
            'Traffic Density: ${density.level.replaceAll('_', ' ').toUpperCase()}',
            style: TextStyle(fontWeight: FontWeight.bold, color: color.withOpacity(0.9)),
          ),
          const Spacer(),
          Text('${density.count} vehicles', style: const TextStyle(color: Colors.grey)),
        ],
      ),
    );
  }

  Widget _buildCountGrid(Map<String, int> counts) {
    return GridView.count(
      crossAxisCount: 4,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      mainAxisSpacing: 10,
      crossAxisSpacing: 10,
      childAspectRatio: 0.85,
      children: counts.entries.map((entry) {
        final color = _vehicleTypeColor(entry.key);
        return Container(
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(14),
            boxShadow: [BoxShadow(color: Colors.black.withOpacity(0.05), blurRadius: 6, offset: const Offset(0, 2))],
          ),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(_vehicleTypeIcon(entry.key), color: color, size: 22),
              const SizedBox(height: 4),
              Text('${entry.value}', style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
              Text(entry.key, style: const TextStyle(fontSize: 10, color: Colors.grey)),
            ],
          ),
        );
      }).toList(),
    );
  }

  Widget _buildVehicleTile(LiveVehicle v) {
    final color = _vehicleTypeColor(v.type);
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        boxShadow: [BoxShadow(color: Colors.black.withOpacity(0.04), blurRadius: 4, offset: const Offset(0, 1))],
      ),
      child: Row(
        children: [
          CircleAvatar(
            backgroundColor: color.withOpacity(0.15),
            child: Icon(_vehicleTypeIcon(v.type), color: color, size: 20),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Text(v.type[0].toUpperCase() + v.type.substring(1), style: const TextStyle(fontWeight: FontWeight.w600)),
                    if (v.plateText != null) ...[
                      const SizedBox(width: 8),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                        decoration: BoxDecoration(
                          color: Colors.blue.shade50,
                          borderRadius: BorderRadius.circular(4),
                          border: Border.all(color: Colors.blue.shade100),
                        ),
                        child: Text(
                          v.plateText!,
                          style: TextStyle(color: Colors.blue.shade800, fontSize: 10, fontWeight: FontWeight.bold, letterSpacing: 0.5),
                        ),
                      ),
                    ],
                  ],
                ),
                Text('ID ${v.id}', style: const TextStyle(color: Colors.grey, fontSize: 12)),
              ],
            ),
          ),
          if (v.speedKmh != null)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
              decoration: BoxDecoration(
                color: v.speedKmh! > 80 ? Colors.red.withOpacity(0.1) : Colors.green.withOpacity(0.1),
                borderRadius: BorderRadius.circular(20),
              ),
              child: Text(
                '${v.speedKmh!.toStringAsFixed(0)} km/h',
                style: TextStyle(
                  color: v.speedKmh! > 80 ? Colors.red : Colors.green.shade700,
                  fontWeight: FontWeight.bold,
                  fontSize: 12,
                ),
              ),
            ),
        ],
      ),
    );
  }
}
