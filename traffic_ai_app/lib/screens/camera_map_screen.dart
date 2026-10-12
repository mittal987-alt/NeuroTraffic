// lib/screens/camera_map_screen.dart
//
// Shows all cameras on a map, color-coded by status (green = online,
// red = offline/error). Uses flutter_map + OpenStreetMap tiles --
// no API key required, unlike Google Maps.

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import '../services/api_service.dart';
import '../widgets/mjpeg_view.dart';
import 'live_view_screen.dart';

class CameraMapScreen extends StatefulWidget {
  const CameraMapScreen({super.key});

  @override
  State<CameraMapScreen> createState() => _CameraMapScreenState();
}

class _CameraMapScreenState extends State<CameraMapScreen> {
  final ApiService _api = ApiService();
  List<TrafficCamera> _cameras = [];
  bool _isLoading = true;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    _loadCameras();
  }

  Future<void> _loadCameras() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });
    try {
      final cameras = await _api.fetchCameras();
      setState(() {
        _cameras = cameras;
        _isLoading = false;
      });
    } catch (e) {
      setState(() {
        _errorMessage = e.toString();
        _isLoading = false;
      });
    }
  }

  Color _statusColor(String status) {
    switch (status) {
      case 'online':
        return Colors.green;
      case 'offline':
        return Colors.grey;
      default:
        return Colors.red;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Camera Map'),
        actions: [IconButton(icon: const Icon(Icons.refresh), onPressed: _loadCameras)],
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : _errorMessage != null
          ? Center(child: Text('Error: $_errorMessage'))
          : _cameras.isEmpty
          ? const Center(child: Text('No cameras registered yet'))
          : FlutterMap(
        options: MapOptions(
          initialCenter: LatLng(_cameras.first.latitude, _cameras.first.longitude),
          initialZoom: 12,
        ),
        children: [
          TileLayer(
            urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
            userAgentPackageName: 'com.example.traffic_ai_app',
          ),
          MarkerLayer(
            markers: _cameras.map((camera) {
              return Marker(
                point: LatLng(camera.latitude, camera.longitude),
                width: 60,
                height: 60,
                child: GestureDetector(
                  onTap: () => _showCameraInfo(camera),
                  child: Icon(Icons.videocam, color: _statusColor(camera.status), size: 36),
                ),
              );
            }).toList(),
          ),
        ],
      ),
    );
  }

  void _showCameraInfo(TrafficCamera camera) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (context) => Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(camera.name, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
                IconButton(
                  icon: const Icon(Icons.fullscreen),
                  onPressed: () {
                    Navigator.of(context).pop();
                    Navigator.of(context).push(MaterialPageRoute(builder: (_) => const LiveViewScreen()));
                  },
                )
              ],
            ),
            const SizedBox(height: 8),
            // Live Preview directly on the Map screen's bottom sheet
            ClipRRect(
              borderRadius: BorderRadius.circular(12),
              child: AspectRatio(
                aspectRatio: 16 / 9,
                child: MjpegView(
                  streamUrl: "${ApiService.baseUrl}/stream/${camera.id}",
                  fit: BoxFit.cover,
                  errorBuilder: (context) => Container(
                    color: Colors.black87,
                    child: const Center(
                      child: Text('Live feed unavailable', style: TextStyle(color: Colors.white70)),
                    ),
                  ),
                ),
              ),
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                Icon(Icons.circle, size: 12, color: _statusColor(camera.status)),
                const SizedBox(width: 6),
                Text('Status: ${camera.status}'),
              ],
            ),
            const SizedBox(height: 4),
            Text('Last seen: ${camera.lastSeen}'),
            const SizedBox(height: 24),
          ],
        ),
      ),
    );
  }
}