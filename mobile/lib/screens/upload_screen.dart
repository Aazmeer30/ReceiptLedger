import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import '../services/api_service.dart';

class UploadScreen extends StatefulWidget {
  const UploadScreen({super.key});

  @override
  State<UploadScreen> createState() => _UploadScreenState();
}

class _UploadScreenState extends State<UploadScreen> {
  final ApiService _api = ApiService();
  final ImagePicker _picker = ImagePicker();

  Uint8List? _selectedImageBytes;
  String? _selectedFileName;
  bool _isLoading = false;
  String? _errorMessage;
  Map<String, dynamic>? _uploadResult;

  Future<void> _pickImage(ImageSource source) async {
    setState(() {
      _errorMessage = null;
    });

    try {
      final XFile? file = await _picker.pickImage(
        source: source,
        imageQuality: 90,
      );
      if (file != null) {
        final bytes = await file.readAsBytes();
        setState(() {
          _selectedImageBytes = bytes;
          _selectedFileName = file.name;
          _uploadResult = null;
        });
      }
    } catch (e) {
      setState(() {
        _errorMessage = 'Failed to pick image: $e';
      });
    }
  }

  Future<void> _uploadReceipt() async {
    if (_selectedImageBytes == null) return;

    setState(() {
      _isLoading = true;
      _errorMessage = null;
      _uploadResult = null;
    });

    try {
      final result = await _api.uploadReceipt(
        bytes: _selectedImageBytes!,
        filename: _selectedFileName ?? 'receipt.jpg',
        deviceTimestamp: DateTime.now().toIso8601String(),
        captureMode: 'single',
      );

      setState(() {
        _uploadResult = result;
        _isLoading = false;
      });
    } catch (e) {
      setState(() {
        _errorMessage = e.toString().replaceAll('Exception: ', '');
        _isLoading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Receipt Capture & OCR'),
        centerTitle: true,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Action Buttons
            Row(
              children: [
                Expanded(
                  child: ElevatedButton.icon(
                    onPressed: _isLoading ? null : () => _pickImage(ImageSource.camera),
                    icon: const Icon(Icons.camera_alt),
                    label: const Text('Take Photo'),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: ElevatedButton.icon(
                    onPressed: _isLoading ? null : () => _pickImage(ImageSource.gallery),
                    icon: const Icon(Icons.photo_library),
                    label: const Text('Gallery'),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),

            // Image Preview Box
            Container(
              height: 240,
              decoration: BoxDecoration(
                color: Colors.grey.shade100,
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: Colors.grey.shade300),
              ),
              clipBehavior: Clip.antiAlias,
              child: _selectedImageBytes != null
                  ? Image.memory(
                      _selectedImageBytes!,
                      fit: BoxFit.contain,
                    )
                  : Center(
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(Icons.receipt_long, size: 56, color: Colors.grey.shade400),
                          const SizedBox(height: 8),
                          Text(
                            'Select or photograph a receipt to test',
                            style: TextStyle(color: Colors.grey.shade600),
                          ),
                        ],
                      ),
                    ),
            ),
            const SizedBox(height: 16),

            // Upload Button
            ElevatedButton(
              onPressed: (_selectedImageBytes != null && !_isLoading) ? _uploadReceipt : null,
              style: ElevatedButton.styleFrom(
                padding: const EdgeInsets.symmetric(vertical: 14),
                backgroundColor: Theme.of(context).primaryColor,
                foregroundColor: Colors.white,
              ),
              child: _isLoading
                  ? const SizedBox(
                      height: 20,
                      width: 20,
                      child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                    )
                  : const Text('Upload & Process Receipt', style: TextStyle(fontSize: 16)),
            ),
            const SizedBox(height: 16),

            // Error display
            if (_errorMessage != null)
              Card(
                color: Colors.red.shade50,
                child: Padding(
                  padding: const EdgeInsets.all(12.0),
                  child: Row(
                    children: [
                      const Icon(Icons.error_outline, color: Colors.red),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Text(
                          _errorMessage!,
                          style: const TextStyle(color: Colors.red, fontWeight: FontWeight.w500),
                        ),
                      ),
                    ],
                  ),
                ),
              ),

            // Results Display
            if (_uploadResult != null) _buildResultCard(_uploadResult!),
          ],
        ),
      ),
    );
  }

  Widget _buildResultCard(Map<String, dynamic> result) {
    final isDup = result['is_duplicate'] == true;
    final status = result['status'] ?? (isDup ? 'DUPLICATE' : 'UNKNOWN');
    final merchant = result['merchant_name'] ?? 'Unknown Merchant';
    final date = result['receipt_date'] ?? 'N/A';
    final total = result['total_amount'] ?? 0.0;
    final conf = (result['confidence_score'] ?? 0.0) as num;
    final receiptType = result['receipt_type'] ?? 'PRINTED';
    final lineItems = (result['line_items'] as List<dynamic>?) ?? [];

    Color statusColor = Colors.green;
    if (status == 'PENDING_REVIEW') statusColor = Colors.orange;
    if (status == 'DUPLICATE' || isDup) statusColor = Colors.purple;

    return Card(
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
                Expanded(
                  child: Text(
                    merchant,
                    style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                  ),
                ),
                Chip(
                  label: Text(
                    status,
                    style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 11),
                  ),
                  backgroundColor: statusColor,
                  padding: EdgeInsets.zero,
                  visualDensity: VisualDensity.compact,
                ),
              ],
            ),
            const Divider(),
            Wrap(
              spacing: 16,
              runSpacing: 6,
              children: [
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.calendar_today_outlined, size: 14, color: Colors.grey.shade600),
                    const SizedBox(width: 4),
                    Text('Date: $date', style: TextStyle(color: Colors.grey.shade700, fontSize: 13)),
                  ],
                ),
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.receipt_outlined, size: 14, color: Colors.grey.shade600),
                    const SizedBox(width: 4),
                    Text('Type: $receiptType', style: TextStyle(color: Colors.grey.shade700, fontSize: 13)),
                  ],
                ),
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.verified_outlined, size: 14, color: Colors.grey.shade600),
                    const SizedBox(width: 4),
                    Text('Conf: ${(conf * 100).toStringAsFixed(1)}%', style: TextStyle(color: Colors.grey.shade700, fontSize: 13)),
                  ],
                ),
              ],
            ),
            const SizedBox(height: 10),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  'Total Amount: Rs. ${total.toString()}',
                  style: const TextStyle(fontSize: 17, fontWeight: FontWeight.bold, color: Colors.blueAccent),
                ),
                if (status == 'PENDING_REVIEW' || isDup)
                  TextButton.icon(
                    onPressed: () {
                      setState(() {
                        _uploadResult = null;
                        _selectedImageBytes = null;
                        _selectedFileName = null;
                      });
                    },
                    icon: const Icon(Icons.refresh, size: 16),
                    label: const Text('Rescan'),
                    style: TextButton.styleFrom(visualDensity: VisualDensity.compact),
                  ),
              ],
            ),
            const SizedBox(height: 10),

            if (isDup)
              Container(
                padding: const EdgeInsets.all(8),
                margin: const EdgeInsets.only(bottom: 8),
                decoration: BoxDecoration(
                  color: Colors.purple.shade50,
                  borderRadius: BorderRadius.circular(6),
                ),
                child: const Row(
                  children: [
                    Icon(Icons.info, color: Colors.purple, size: 18),
                    SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        'Deduplication Layer Detected: This receipt was already submitted earlier.',
                        style: TextStyle(color: Colors.purple, fontSize: 12),
                      ),
                    ),
                  ],
                ),
              ),

            Text(
              'Extracted Items (${lineItems.length}):',
              style: const TextStyle(fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 6),
            if (lineItems.isEmpty)
              const Text('No line items extracted (or flagged as duplicate/empty).', style: TextStyle(color: Colors.grey))
            else
              Table(
                columnWidths: const {
                  0: FlexColumnWidth(3),
                  1: FlexColumnWidth(1.5),
                  2: FlexColumnWidth(2),
                },
                children: [
                  TableRow(
                    decoration: BoxDecoration(color: Colors.grey.shade200),
                    children: const [
                      Padding(padding: EdgeInsets.all(6), child: Text('Item', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12))),
                      Padding(padding: EdgeInsets.all(6), child: Text('Qty', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12))),
                      Padding(padding: EdgeInsets.all(6), child: Text('Total', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12))),
                    ],
                  ),
                  ...lineItems.map((item) {
                    final name = item['canonical_name'] ?? item['item_name'] ?? 'Item';
                    final qty = '${item['quantity'] ?? 1} ${item['unit'] ?? ''}'.trim();
                    final price = 'Rs. ${item['total_price'] ?? 0}';
                    return TableRow(
                      children: [
                        Padding(padding: const EdgeInsets.all(6), child: Text(name, style: const TextStyle(fontSize: 12))),
                        Padding(padding: const EdgeInsets.all(6), child: Text(qty, style: const TextStyle(fontSize: 12))),
                        Padding(padding: const EdgeInsets.all(6), child: Text(price, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600))),
                      ],
                    );
                  }),
                ],
              ),
          ],
        ),
      ),
    );
  }
}
