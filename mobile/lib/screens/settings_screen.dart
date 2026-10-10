import 'package:flutter/material.dart';
import '../services/api_service.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  final ApiService _api = ApiService();
  late TextEditingController _urlController;

  bool _isChecking = false;
  Map<String, dynamic>? _healthData;
  String? _healthError;

  @override
  void initState() {
    super.initState();
    _urlController = TextEditingController(text: _api.baseUrl);
    _checkHealth();
  }

  Future<void> _checkHealth() async {
    setState(() {
      _isChecking = true;
      _healthError = null;
    });

    try {
      final data = await _api.checkHealth();
      setState(() {
        _healthData = data;
        _isChecking = false;
      });
    } catch (e) {
      setState(() {
        _healthError = e.toString().replaceAll('Exception: ', '');
        _isChecking = false;
        _healthData = null;
      });
    }
  }

  void _saveUrl() {
    _api.setBaseUrl(_urlController.text.trim());
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('API Base URL updated!'), backgroundColor: Colors.blue),
    );
    _checkHealth();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Backend & Engine Settings'),
        centerTitle: true,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Backend Connectivity Status Card
            Card(
              elevation: 2,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
              child: Padding(
                padding: const EdgeInsets.all(16.0),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        const Text('Backend Health', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
                        IconButton(
                          icon: const Icon(Icons.refresh),
                          onPressed: _isChecking ? null : _checkHealth,
                          tooltip: 'Probe Backend',
                        ),
                      ],
                    ),
                    const Divider(),
                    if (_isChecking)
                      const Padding(
                        padding: EdgeInsets.symmetric(vertical: 12),
                        child: Center(child: CircularProgressIndicator()),
                      )
                    else if (_healthError != null)
                      Row(
                        children: [
                          const Icon(Icons.cancel, color: Colors.red),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              'Unreachable: $_healthError',
                              style: const TextStyle(color: Colors.red, fontWeight: FontWeight.w500),
                            ),
                          ),
                        ],
                      )
                    else if (_healthData != null) ...[
                      Row(
                        children: [
                          const Icon(Icons.check_circle, color: Colors.green),
                          const SizedBox(width: 8),
                          Text(
                            'Operational (${_healthData!['status']})',
                            style: const TextStyle(color: Colors.green, fontWeight: FontWeight.bold),
                          ),
                        ],
                      ),
                      const SizedBox(height: 12),
                      const Text('Engine Status:', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13)),
                      const SizedBox(height: 6),
                      _buildEngineRow('Google Cloud Vision', _healthData!['engines']?['cloud_vision'] ?? 'N/A'),
                      _buildEngineRow('Tesseract OCR', _healthData!['engines']?['tesseract'] ?? 'N/A'),
                      _buildEngineRow('EasyOCR (Handwritten)', _healthData!['engines']?['easyocr'] ?? 'N/A'),
                      _buildEngineRow('Database', _healthData!['engines']?['database'] ?? 'N/A'),
                    ],
                  ],
                ),
              ),
            ),
            const SizedBox(height: 20),

            // Server URL Configuration Card
            Card(
              elevation: 2,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
              child: Padding(
                padding: const EdgeInsets.all(16.0),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('API Endpoint Configuration', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
                    const SizedBox(height: 6),
                    Text(
                      'Set the URL where your FastAPI backend is running.',
                      style: TextStyle(color: Colors.grey.shade600, fontSize: 13),
                    ),
                    const SizedBox(height: 14),
                    TextField(
                      controller: _urlController,
                      decoration: const InputDecoration(
                        labelText: 'API Base URL',
                        border: OutlineInputBorder(),
                        prefixIcon: Icon(Icons.link),
                      ),
                    ),
                    const SizedBox(height: 12),
                    ElevatedButton.icon(
                      onPressed: _saveUrl,
                      icon: const Icon(Icons.save),
                      label: const Text('Save & Test Connection'),
                      style: ElevatedButton.styleFrom(
                        padding: const EdgeInsets.symmetric(vertical: 12),
                      ),
                    ),
                    const SizedBox(height: 12),
                    const Text('Quick Presets:', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12)),
                    const SizedBox(height: 6),
                    Wrap(
                      spacing: 8,
                      children: [
                        ActionChip(
                          label: const Text('PC Wi-Fi (192.168.100.78:8000)'),
                          onPressed: () {
                            _urlController.text = 'http://192.168.100.78:8000';
                            _saveUrl();
                          },
                        ),
                        ActionChip(
                          label: const Text('Android Emulator (10.0.2.2:8000)'),
                          onPressed: () {
                            _urlController.text = 'http://10.0.2.2:8000';
                            _saveUrl();
                          },
                        ),
                        ActionChip(
                          label: const Text('Localhost (127.0.0.1:8000)'),
                          onPressed: () {
                            _urlController.text = 'http://127.0.0.1:8000';
                            _saveUrl();
                          },
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildEngineRow(String name, String status) {
    Color color = Colors.grey.shade800;
    if (status.startsWith('ok')) color = Colors.green.shade800;
    if (status.startsWith('not_installed') || status.startsWith('disabled')) color = Colors.grey.shade600;

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3.0),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(name, style: const TextStyle(fontSize: 12)),
          Text(status, style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: color)),
        ],
      ),
    );
  }
}
