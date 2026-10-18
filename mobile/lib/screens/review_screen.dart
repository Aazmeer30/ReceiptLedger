import 'package:flutter/material.dart';
import '../services/api_service.dart';

class ReviewScreen extends StatefulWidget {
  const ReviewScreen({super.key});

  @override
  State<ReviewScreen> createState() => _ReviewScreenState();
}

class _ReviewScreenState extends State<ReviewScreen> {
  final ApiService _api = ApiService();
  bool _isLoading = true;
  String? _errorMessage;
  List<Map<String, dynamic>> _queueItems = [];

  @override
  void initState() {
    super.initState();
    _loadQueue();
  }

  Future<void> _loadQueue() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      final list = await _api.getReviewQueue();
      setState(() {
        _queueItems = list;
        _isLoading = false;
      });
    } catch (e) {
      setState(() {
        _errorMessage = e.toString().replaceAll('Exception: ', '');
        _isLoading = false;
      });
    }
  }

  Future<void> _resolveItem(Map<String, dynamic> item, String action, String name, double total) async {
    final queueId = item['id'];
    try {
      await _api.resolveReviewItem(queueId, {
        'action': action,
        'confirmed_name': name,
        'confirmed_total_price': total,
      });

      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Item marked as $action!'), backgroundColor: Colors.green),
      );
      _loadQueue();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Failed: $e'), backgroundColor: Colors.red),
      );
    }
  }

  void _showEditDialog(Map<String, dynamic> item) {
    final li = item['line_item'] ?? {};
    final queueId = item['id']?.toString() ?? '';
    final nameController = TextEditingController(text: li['item_name'] ?? item['candidate_text'] ?? '');
    final priceController = TextEditingController(text: (li['total_price'] ?? 0.0).toString());

    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Review Line Item'),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (queueId.isNotEmpty) ...[
                ClipRRect(
                  borderRadius: BorderRadius.circular(6),
                  child: Image.network(
                    _api.getReviewItemCropUrl(queueId),
                    height: 80,
                    width: double.infinity,
                    fit: BoxFit.contain,
                    errorBuilder: (_, __, ___) => const SizedBox.shrink(),
                  ),
                ),
                const SizedBox(height: 8),
              ],
              Text('Raw OCR Candidate: ${item['candidate_text']}', style: TextStyle(color: Colors.grey.shade600, fontSize: 12)),
              const SizedBox(height: 12),
              TextField(
                controller: nameController,
                decoration: const InputDecoration(labelText: 'Confirmed Item Name', border: OutlineInputBorder()),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: priceController,
                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                decoration: const InputDecoration(labelText: 'Confirmed Total Price (Rs.)', border: OutlineInputBorder()),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Cancel'),
          ),
          ElevatedButton(
            onPressed: () {
              Navigator.pop(ctx);
              final total = double.tryParse(priceController.text) ?? 0.0;
              _resolveItem(item, 'EDITED', nameController.text.trim(), total);
            },
            child: const Text('Confirm & Save'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Review Queue (Low Conf)'),
        centerTitle: true,
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loadQueue,
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
              ElevatedButton(onPressed: _loadQueue, child: const Text('Retry')),
            ],
          ),
        ),
      );
    }

    if (_queueItems.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.check_circle_outline, size: 64, color: Colors.green.shade400),
            const SizedBox(height: 12),
            const Text('All items verified!', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: 6),
            Text('No receipts currently need human-in-the-loop review.', style: TextStyle(color: Colors.grey.shade600)),
          ],
        ),
      );
    }

    return RefreshIndicator(
      onRefresh: _loadQueue,
      child: ListView.separated(
        padding: const EdgeInsets.all(12),
        itemCount: _queueItems.length,
        separatorBuilder: (_, __) => const SizedBox(height: 8),
        itemBuilder: (context, index) {
          final item = _queueItems[index];
          final candidate = item['candidate_text'] ?? 'Unknown';
          final conf = (item['model_confidence'] ?? 0.0) as num;
          final li = item['line_item'] ?? {};
          final currentName = li['item_name'] ?? candidate;
          final currentPrice = li['total_price'] ?? 0.0;
          final merchant = item['merchant_name'] ?? 'Store';

          return Card(
            elevation: 2,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
            child: Padding(
              padding: const EdgeInsets.all(14.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(merchant, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14)),
                      Chip(
                        label: Text(
                          'Conf: ${(conf * 100).toStringAsFixed(1)}%',
                          style: const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.bold),
                        ),
                        backgroundColor: Colors.orange,
                        visualDensity: VisualDensity.compact,
                        padding: EdgeInsets.zero,
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  ClipRRect(
                    borderRadius: BorderRadius.circular(6),
                    child: Container(
                      color: Colors.grey.shade100,
                      child: Image.network(
                        _api.getReviewItemCropUrl(item['id']?.toString() ?? ''),
                        height: 75,
                        width: double.infinity,
                        fit: BoxFit.contain,
                        errorBuilder: (_, __, ___) => const SizedBox.shrink(),
                      ),
                    ),
                  ),
                  const SizedBox(height: 6),
                  Text('Raw OCR: "$candidate"', style: TextStyle(color: Colors.grey.shade700, fontStyle: FontStyle.italic)),
                  const SizedBox(height: 4),
                  Text('Normalized: $currentName  •  Rs. $currentPrice', style: const TextStyle(fontWeight: FontWeight.w600)),
                  const SizedBox(height: 12),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.end,
                    children: [
                      TextButton.icon(
                        onPressed: () => _showEditDialog(item),
                        icon: const Icon(Icons.edit, size: 16),
                        label: const Text('Edit / Correct'),
                      ),
                      const SizedBox(width: 8),
                      ElevatedButton.icon(
                        onPressed: () => _resolveItem(item, 'ACCEPTED', currentName, (currentPrice as num).toDouble()),
                        icon: const Icon(Icons.check, size: 16),
                        label: const Text('Accept'),
                        style: ElevatedButton.styleFrom(backgroundColor: Colors.green, foregroundColor: Colors.white),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }
}
