import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';

class ApiService {
  static final ApiService _instance = ApiService._internal();
  factory ApiService() => _instance;
  ApiService._internal();

  String _baseUrl = 'http://192.168.100.78:8000';

  String get baseUrl => _baseUrl;

  void init() {
    try {
      final envUrl = dotenv.env['API_BASE_URL'];
      if (envUrl != null && envUrl.isNotEmpty) {
        // If running in Android emulator and URL points to localhost/127.0.0.1, translate to 10.0.2.2
        if (!kIsWeb && defaultTargetPlatform == TargetPlatform.android &&
            (envUrl.contains('127.0.0.1') || envUrl.contains('localhost'))) {
          _baseUrl = envUrl.replaceAll('127.0.0.1', '10.0.2.2').replaceAll('localhost', '10.0.2.2');
        } else {
          _baseUrl = envUrl;
        }
      } else {
        // Fallback: Wi-Fi host IP for physical device, 10.0.2.2 for emulator
        if (!kIsWeb && defaultTargetPlatform == TargetPlatform.android) {
          _baseUrl = 'http://192.168.100.78:8000';
        }
      }
    } catch (_) {
      // Fallback default
      _baseUrl = 'http://192.168.100.78:8000';
    }
  }

  void setBaseUrl(String newUrl) {
    _baseUrl = newUrl.trim().replaceAll(RegExp(r'/+$'), '');
  }

  /// Probes GET /api/v1/health
  Future<Map<String, dynamic>> checkHealth() async {
    final url = Uri.parse('$_baseUrl/api/v1/health');
    final response = await http.get(url).timeout(const Duration(seconds: 5));
    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    }
    throw Exception('Health check failed with status ${response.statusCode}');
  }

  /// Uploads receipt image via multipart POST /api/v1/receipts/upload
  Future<Map<String, dynamic>> uploadReceipt({
    required Uint8List bytes,
    required String filename,
    String? deviceTimestamp,
    String captureMode = 'single',
  }) async {
    final url = Uri.parse('$_baseUrl/api/v1/receipts/upload');
    final request = http.MultipartRequest('POST', url);

    final ext = filename.toLowerCase();
    String mimeSubtype = 'jpeg';
    if (ext.endsWith('.png')) {
      mimeSubtype = 'png';
    } else if (ext.endsWith('.webp')) {
      mimeSubtype = 'webp';
    }

    request.files.add(
      http.MultipartFile.fromBytes(
        'file',
        bytes,
        filename: filename,
        contentType: MediaType('image', mimeSubtype),
      ),
    );

    if (deviceTimestamp != null) {
      request.fields['device_timestamp'] = deviceTimestamp;
    }
    request.fields['capture_mode'] = captureMode;

    final streamedResponse = await request.send().timeout(const Duration(seconds: 30));
    final responseBody = await streamedResponse.stream.bytesToString();
    final decoded = jsonDecode(responseBody) as Map<String, dynamic>;

    if (streamedResponse.statusCode == 200) {
      return decoded;
    } else if (streamedResponse.statusCode == 409) {
      // Duplicate receipt response
      return {
        ...decoded,
        'is_duplicate': true,
        'error_message': 'Duplicate receipt already exists in ledger',
      };
    } else {
      final detail = decoded['detail'] ?? 'Upload failed (${streamedResponse.statusCode})';
      throw Exception(detail.toString());
    }
  }

  /// Fetches paginated ledger receipts GET /api/v1/analytics/receipts
  Future<List<Map<String, dynamic>>> getReceipts({int page = 1, int pageSize = 50}) async {
    final url = Uri.parse('$_baseUrl/api/v1/analytics/receipts?page=$page&page_size=$pageSize');
    final response = await http.get(url).timeout(const Duration(seconds: 10));
    if (response.statusCode == 200) {
      final data = jsonDecode(response.body);
      final list = data['receipts'] as List<dynamic>? ?? [];
      return list.cast<Map<String, dynamic>>();
    }
    throw Exception('Failed to load receipts: ${response.statusCode}');
  }

  /// Fetches monthly analytics summary GET /api/v1/analytics/monthly
  Future<Map<String, dynamic>> getMonthlySummary({required int year, required int month}) async {
    final url = Uri.parse('$_baseUrl/api/v1/analytics/monthly?year=$year&month=$month');
    final response = await http.get(url).timeout(const Duration(seconds: 10));
    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    }
    throw Exception('Failed to load monthly summary: ${response.statusCode}');
  }

  /// Fetches items pending human review GET /api/v1/review-queue
  Future<List<Map<String, dynamic>>> getReviewQueue() async {
    final url = Uri.parse('$_baseUrl/api/v1/review-queue');
    final response = await http.get(url).timeout(const Duration(seconds: 10));
    if (response.statusCode == 200) {
      final list = jsonDecode(response.body) as List<dynamic>? ?? [];
      return list.cast<Map<String, dynamic>>();
    }
    throw Exception('Failed to load review queue: ${response.statusCode}');
  }

  /// Resolves an item in the review queue PATCH /api/v1/review-queue/{id}
  Future<Map<String, dynamic>> resolveReviewItem(String queueId, Map<String, dynamic> payload) async {
    final url = Uri.parse('$_baseUrl/api/v1/review-queue/$queueId');
    final response = await http.patch(
      url,
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(payload),
    ).timeout(const Duration(seconds: 10));

    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    }
    throw Exception('Failed to resolve review item: ${response.statusCode}');
  }

  /// Returns URL to fetch preprocessed receipt image GET /api/v1/receipts/{id}/image
  String getReceiptImageUrl(String receiptId, {bool signedUrl = false}) {
    final query = signedUrl ? '?signed_url=true' : '';
    return '$_baseUrl/api/v1/receipts/$receiptId/image$query';
  }

  /// Returns URL to fetch visual crop snippet for flagged item GET /api/v1/review-queue/{id}/crop
  String getReviewItemCropUrl(String queueId) {
    return '$_baseUrl/api/v1/review-queue/$queueId/crop';
  }

  /// Returns URL to download CSV ledger export GET /api/v1/analytics/export?format=csv
  String getExportCsvUrl({int? year, int? month}) {
    String query = 'format=csv';
    if (year != null) query += '&year=$year';
    if (month != null) query += '&month=$month';
    return '$_baseUrl/api/v1/analytics/export?$query';
  }
}
