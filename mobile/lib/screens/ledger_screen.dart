import 'package:flutter/material.dart';
import '../services/api_service.dart';

class LedgerScreen extends StatefulWidget {
  const LedgerScreen({super.key});

  @override
  State<LedgerScreen> createState() => _LedgerScreenState();
}

class _LedgerScreenState extends State<LedgerScreen> {
  final ApiService _api = ApiService();
  bool _isLoading = true;
  String? _errorMessage;
  List<Map<String, dynamic>> _receipts = [];

  @override
  void initState() {
    super.initState();
    _loadReceipts();
  }

  Future<void> _loadReceipts() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      final list = await _api.getReceipts();
      setState(() {
        _receipts = list;
        _isLoading = false;
      });
    } catch (e) {
      setState(() {
        _errorMessage = e.toString().replaceAll('Exception: ', '');
        _isLoading = false;
      });
    }
  }

  void _showExportDialog() {
    final exportUrl = _api.getExportCsvUrl();
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Export Ledger CSV'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Download the full categorized ledger spreadsheet:'),
            const SizedBox(height: 10),
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: Colors.grey.shade100,
                borderRadius: BorderRadius.circular(6),
              ),
              child: SelectableText(
                exportUrl,
                style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 12, color: Colors.blueAccent),
              ),
            ),
            const SizedBox(height: 10),
            Text(
              'Open this link in any browser on your network to stream receiptledger_export_all.csv directly.',
              style: TextStyle(color: Colors.grey.shade600, fontSize: 12),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Close'),
          ),
        ],
      ),
    );
  }

  void _viewReceiptImage(String receiptId, String merchant) {
    final imgUrl = _api.getReceiptImageUrl(receiptId);
    showDialog(
      context: context,
      builder: (ctx) => Dialog(
        insetPadding: const EdgeInsets.all(16),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Expanded(
                    child: Text(
                      merchant,
                      style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  IconButton(
                    icon: const Icon(Icons.close),
                    onPressed: () => Navigator.pop(ctx),
                    visualDensity: VisualDensity.compact,
                  ),
                ],
              ),
            ),
            const Divider(height: 1),
            Flexible(
              child: InteractiveViewer(
                child: Image.network(
                  imgUrl,
                  fit: BoxFit.contain,
                  loadingBuilder: (ctx, child, progress) {
                    if (progress == null) return child;
                    return const SizedBox(
                      height: 250,
                      child: Center(child: CircularProgressIndicator()),
                    );
                  },
                  errorBuilder: (ctx, err, stack) => const Padding(
                    padding: EdgeInsets.all(32.0),
                    child: Center(
                      child: Text(
                        'Image not found on server or storage bucket.',
                        textAlign: TextAlign.center,
                        style: TextStyle(color: Colors.grey),
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Receipt Ledger'),
        centerTitle: true,
        actions: [
          IconButton(
            icon: const Icon(Icons.file_download_outlined),
            onPressed: _showExportDialog,
            tooltip: 'Export CSV',
          ),
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loadReceipts,
            tooltip: 'Refresh',
          ),
        ],
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
              const Icon(Icons.error_outline, size: 48, color: Colors.red),
              const SizedBox(height: 12),
              Text(_errorMessage!, textAlign: TextAlign.center, style: const TextStyle(color: Colors.red)),
              const SizedBox(height: 16),
              ElevatedButton(onPressed: _loadReceipts, child: const Text('Retry')),
            ],
          ),
        ),
      );
    }

    if (_receipts.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.inbox, size: 64, color: Colors.grey.shade400),
            const SizedBox(height: 12),
            const Text('No receipts in ledger yet', style: TextStyle(fontSize: 16, color: Colors.grey)),
            const SizedBox(height: 8),
            const Text('Upload a receipt on the Upload tab to see it here.', style: TextStyle(color: Colors.grey)),
          ],
        ),
      );
    }

    return RefreshIndicator(
      onRefresh: _loadReceipts,
      child: ListView.separated(
        padding: const EdgeInsets.all(12),
        itemCount: _receipts.length,
        separatorBuilder: (_, __) => const SizedBox(height: 8),
        itemBuilder: (context, index) {
          final r = _receipts[index];
          final merchant = r['merchant_name'] ?? 'Unknown Merchant';
          final date = r['receipt_date'] ?? 'N/A';
          final total = r['total_amount'] ?? 0.0;
          final status = r['status'] ?? 'PROCESSED';
          final type = r['receipt_type'] ?? 'PRINTED';
          final lineItems = (r['line_items'] as List<dynamic>?) ?? [];

          Color chipColor = Colors.green;
          if (status == 'PENDING_REVIEW') chipColor = Colors.orange;
          if (status == 'DUPLICATE') chipColor = Colors.purple;

          return Card(
            elevation: 1,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
            child: ExpansionTile(
              leading: CircleAvatar(
                backgroundColor: Colors.blue.shade50,
                child: Icon(
                  type == 'PRINTED' ? Icons.receipt : Icons.edit_note,
                  color: Colors.blueAccent,
                ),
              ),
              title: Text(merchant, style: const TextStyle(fontWeight: FontWeight.bold)),
              subtitle: Text('$date • Rs. $total'),
              trailing: Chip(
                label: Text(
                  status,
                  style: const TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.bold),
                ),
                backgroundColor: chipColor,
                visualDensity: VisualDensity.compact,
                padding: EdgeInsets.zero,
              ),
              children: [
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 8.0),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Divider(),
                      Text('Line Items (${lineItems.length}):', style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13)),
                      const SizedBox(height: 4),
                      if (lineItems.isEmpty)
                        const Text('No line items recorded', style: TextStyle(color: Colors.grey, fontSize: 12))
                      else
                        ...lineItems.map((item) {
                          final name = item['canonical_name'] ?? item['item_name'] ?? 'Item';
                          final qty = '${item['quantity'] ?? 1} ${item['unit'] ?? ''}'.trim();
                          final price = 'Rs. ${item['total_price'] ?? 0}';
                          return Padding(
                            padding: const EdgeInsets.symmetric(vertical: 2.0),
                            child: Row(
                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                              children: [
                                Expanded(child: Text('$name ($qty)', style: const TextStyle(fontSize: 12))),
                                Text(price, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
                              ],
                            ),
                          );
                        }),
                      const SizedBox(height: 12),
                      SizedBox(
                        width: double.infinity,
                        child: OutlinedButton.icon(
                          onPressed: () => _viewReceiptImage(r['id']?.toString() ?? '', merchant),
                          icon: const Icon(Icons.photo_library_outlined, size: 16),
                          label: const Text('View Receipt Photo'),
                          style: OutlinedButton.styleFrom(
                            visualDensity: VisualDensity.compact,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}
