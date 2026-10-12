// lib/screens/analytics_screen.dart
//
// Analytics Dashboard: hourly traffic trend (bar chart) and alert
// type breakdown (bar chart), pulled from the backend's /analytics
// endpoints.

import 'package:flutter/material.dart';
import 'package:fl_chart/fl_chart.dart';
import '../services/api_service.dart';

class AnalyticsScreen extends StatefulWidget {
  const AnalyticsScreen({super.key});

  @override
  State<AnalyticsScreen> createState() => _AnalyticsScreenState();
}

class _AnalyticsScreenState extends State<AnalyticsScreen> {
  final ApiService _api = ApiService();

  List<Map<String, dynamic>> _hourlyData = [];
  List<Map<String, dynamic>> _alertData = [];
  List<Map<String, dynamic>> _vehicleTypeData = [];
  bool _isLoading = true;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    _loadData();
  }

  Future<void> _loadData() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });
    try {
      final results = await Future.wait([
        _api.fetchHourlyTraffic(),
        _api.fetchAlertBreakdown(),
        _api.fetchVehicleTypeBreakdown(),
      ]);
      setState(() {
        _hourlyData = results[0];
        _alertData = results[1];
        _vehicleTypeData = results[2];
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
        title: const Text('Analytics'),
        actions: [IconButton(icon: const Icon(Icons.refresh), onPressed: _loadData)],
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : _errorMessage != null
          ? Center(child: Text('Error: $_errorMessage'))
          : RefreshIndicator(
        onRefresh: _loadData,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            const Text('Hourly Traffic', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            _buildHourlyChart(),
            const SizedBox(height: 32),
            const Text('Alerts by Type', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            _buildAlertChart(),
            const SizedBox(height: 32),
            const Text('Vehicles by Type', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            _buildVehicleTypeChart(),
          ],
        ),
      ),
    );
  }

  Widget _buildHourlyChart() {
    if (_hourlyData.isEmpty) {
      return const SizedBox(height: 150, child: Center(child: Text('No data yet')));
    }
    return SizedBox(
      height: 200,
      child: BarChart(
        BarChartData(
          barGroups: _hourlyData.asMap().entries.map((entry) {
            final index = entry.key;
            final count = (entry.value['count'] as num).toDouble();
            return BarChartGroupData(x: index, barRods: [BarChartRodData(toY: count, color: Colors.blue)]);
          }).toList(),
          titlesData: FlTitlesData(
            bottomTitles: AxisTitles(
              sideTitles: SideTitles(
                showTitles: true,
                getTitlesWidget: (value, meta) {
                  final index = value.toInt();
                  if (index < 0 || index >= _hourlyData.length) return const SizedBox();
                  // Show just the hour portion (e.g. "14:00") from the ISO timestamp
                  final hourStr = _hourlyData[index]['hour'] as String;
                  final hourLabel = hourStr.length >= 13 ? hourStr.substring(11, 13) : '';
                  return Text(hourLabel, style: const TextStyle(fontSize: 10));
                },
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildAlertChart() {
    if (_alertData.isEmpty) {
      return const SizedBox(height: 100, child: Center(child: Text('No alerts yet')));
    }
    return SizedBox(
      height: 200,
      child: BarChart(
        BarChartData(
          barGroups: _alertData.asMap().entries.map((entry) {
            final index = entry.key;
            final count = (entry.value['count'] as num).toDouble();
            return BarChartGroupData(x: index, barRods: [BarChartRodData(toY: count, color: Colors.red)]);
          }).toList(),
          titlesData: FlTitlesData(
            bottomTitles: AxisTitles(
              sideTitles: SideTitles(
                showTitles: true,
                getTitlesWidget: (value, meta) {
                  final index = value.toInt();
                  if (index < 0 || index >= _alertData.length) return const SizedBox();
                  return Text(_alertData[index]['alert_type'], style: const TextStyle(fontSize: 9));
                },
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildVehicleTypeChart() {
    if (_vehicleTypeData.isEmpty) {
      return const SizedBox(height: 100, child: Center(child: Text('No data yet')));
    }
    return SizedBox(
      height: 200,
      child: BarChart(
        BarChartData(
          barGroups: _vehicleTypeData.asMap().entries.map((entry) {
            final index = entry.key;
            final count = (entry.value['count'] as num).toDouble();
            return BarChartGroupData(x: index, barRods: [BarChartRodData(toY: count, color: Colors.green)]);
          }).toList(),
          titlesData: FlTitlesData(
            bottomTitles: AxisTitles(
              sideTitles: SideTitles(
                showTitles: true,
                getTitlesWidget: (value, meta) {
                  final index = value.toInt();
                  if (index < 0 || index >= _vehicleTypeData.length) return const SizedBox();
                  return Text(_vehicleTypeData[index]['vehicle_type'], style: const TextStyle(fontSize: 9));
                },
              ),
            ),
          ),
        ),
      ),
    );
  }
}