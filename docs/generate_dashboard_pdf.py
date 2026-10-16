import base64
import io
import subprocess
from pathlib import Path
from PIL import Image

docs_dir = Path(__file__).resolve().parent
repo_root = docs_dir.parent

def encode_img_b64(path, max_width=850, quality=85):
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Image not found: {p}")
    im = Image.open(p).convert("RGB")
    if im.width > max_width:
        ratio = max_width / float(im.width)
        new_height = int(float(im.height) * ratio)
        im = im.resize((max_width, new_height), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=quality, optimize=True)
    return base64.b64encode(buf.getvalue()).decode("utf-8")

b64_review_queue = encode_img_b64(docs_dir / "assets" / "barebones_screenshots" / "04_review_queue_barebones.jpg")
b64_javed_nahari = encode_img_b64(repo_root / "data" / "sample_receipts" / "javed_nahari_sample.png")
b64_metro_safari = encode_img_b64(repo_root / "data" / "sample_receipts" / "metro_safari_park_sample.png")

html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>ReceiptLedger – Web Operations Console & Dashboard Design Brief</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');
  
  @page {{
    size: A4 portrait;
    margin: 12mm 12mm 12mm 12mm;
  }}

  body {{
    font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    color: #0F172A;
    background: #FFFFFF;
    line-height: 1.45;
    font-size: 8pt;
    margin: 0;
    padding: 0;
  }}

  h1, h2, h3, h4 {{
    color: #0F172A;
    font-weight: 700;
    page-break-after: avoid;
    margin-top: 10pt;
    margin-bottom: 4pt;
  }}

  h1 {{
    font-size: 19pt;
    margin-top: 0;
    margin-bottom: 2pt;
    letter-spacing: -0.5px;
  }}

  .subtitle {{
    font-size: 9.5pt;
    color: #475569;
    margin-bottom: 8pt;
    border-bottom: 2px solid #E2E8F0;
    padding-bottom: 4pt;
  }}

  .badge-row {{
    margin-bottom: 8pt;
  }}

  .badge {{
    display: inline-block;
    padding: 2pt 5pt;
    font-size: 7pt;
    font-weight: 600;
    border-radius: 3pt;
    margin-right: 3pt;
    background: #F1F5F9;
    color: #334155;
    border: 1px solid #CBD5E1;
  }}

  .badge-primary {{
    background: #0F172A;
    color: #FFFFFF;
    border-color: #0F172A;
  }}

  table {{
    width: 100%;
    border-collapse: collapse;
    margin: 4pt 0 7pt 0;
    font-size: 7.2pt;
    page-break-inside: avoid;
  }}

  th, td {{
    padding: 3.5pt 5pt;
    text-align: left;
    border-bottom: 1px solid #E2E8F0;
  }}

  th {{
    background: #F8FAFC;
    color: #0F172A;
    font-weight: 700;
    border-top: 1.5px solid #CBD5E1;
    border-bottom: 1.5px solid #CBD5E1;
  }}

  .mono-box {{
    background: #F8FAFC;
    border: 1px solid #CBD5E1;
    border-radius: 4pt;
    padding: 5pt 7pt;
    margin: 4pt 0 6pt 0;
    font-family: 'JetBrains Mono', monospace;
    font-size: 6.5pt;
    line-height: 1.35;
    page-break-inside: avoid;
    white-space: pre-wrap;
    color: #1E293B;
  }}

  .wireframe-container {{
    border: 1.5px solid #0F172A;
    background: #F8FAFC;
    border-radius: 4pt;
    padding: 6pt;
    margin: 6pt 0 8pt 0;
    page-break-inside: avoid;
  }}

  .wireframe-header {{
    background: #0F172A;
    color: #FFFFFF;
    padding: 4pt 6pt;
    font-size: 7pt;
    font-weight: 700;
    border-radius: 2pt;
    display: flex;
    justify-content: space-between;
    margin-bottom: 4pt;
  }}

  .wireframe-kpis {{
    display: flex;
    gap: 4pt;
    margin-bottom: 4pt;
  }}

  .wireframe-kpi {{
    flex: 1;
    background: #FFFFFF;
    border: 1px solid #CBD5E1;
    padding: 3pt 5pt;
    border-radius: 2pt;
  }}

  .wireframe-kpi-val {{
    font-size: 8.5pt;
    font-weight: 800;
    color: #0F172A;
  }}

  .wireframe-kpi-lbl {{
    font-size: 6pt;
    color: #64748B;
    text-transform: uppercase;
  }}

  .wireframe-split {{
    display: flex;
    gap: 4pt;
    margin-bottom: 4pt;
  }}

  .wireframe-pane {{
    flex: 1;
    background: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 2pt;
    padding: 4pt;
  }}

  .wireframe-pane-title {{
    font-weight: 700;
    font-size: 6.8pt;
    color: #0F172A;
    border-bottom: 1px solid #E2E8F0;
    padding-bottom: 2pt;
    margin-bottom: 3pt;
  }}

  .image-showcase {{
    display: flex;
    gap: 8pt;
    margin: 6pt 0;
    page-break-inside: avoid;
  }}

  .image-card {{
    flex: 1;
    border: 1px solid #CBD5E1;
    border-radius: 4pt;
    padding: 5pt;
    background: #FFFFFF;
    text-align: center;
  }}

  .image-card img {{
    max-width: 100%;
    max-height: 140pt;
    object-fit: contain;
    border: 1px solid #E2E8F0;
    border-radius: 2pt;
  }}

  .image-title {{
    font-weight: 700;
    font-size: 7.2pt;
    color: #0F172A;
    margin-top: 3pt;
    text-align: left;
  }}

  .image-desc {{
    font-size: 6.5pt;
    color: #475569;
    text-align: left;
    margin-top: 1pt;
  }}

  .code-json {{
    background: #0F172A;
    color: #E2E8F0;
    border-radius: 3.5pt;
    padding: 4pt 6pt;
    font-family: 'JetBrains Mono', monospace;
    font-size: 6.5pt;
    line-height: 1.3;
    white-space: pre-wrap;
    margin: 3pt 0 5pt 0;
    page-break-inside: avoid;
  }}

  .flow-box {{
    background: #F1F5F9;
    border-left: 3px solid #0F172A;
    padding: 4pt 6pt;
    font-family: 'JetBrains Mono', monospace;
    font-size: 6.5pt;
    line-height: 1.35;
    margin: 4pt 0 6pt 0;
    page-break-inside: avoid;
  }}

  .page-break {{
    page-break-before: always;
  }}
</style>
</head>
<body>

<h1>ReceiptLedger</h1>
<div class="subtitle">Web Operations Console & Desktop Dashboard Design Brief</div>

<div class="badge-row">
  <span class="badge badge-primary">Monorepo: web/ (React 18 + Vite)</span>
  <span class="badge">API Gateway: http://localhost:8000/api/v1</span>
  <span class="badge">Scope: Admin, Audit & Triage</span>
  <span class="badge">Form Factor: Desktop (1280px+)</span>
  <span class="badge">Design Constraint: Zero Gradients | Zero Glass</span>
</div>

<h2>1. System Role & Architecture Overview</h2>
<p>The Web Dashboard is the <strong>central desktop operations, audit, and financial intelligence console</strong> for ReceiptLedger. While the mobile client handles quick on-the-go receipt photography, the desktop console provides high-detail verification, audit logging, and observability for household finances or business bookkeeping.</p>

<table>
  <thead>
    <tr>
      <th>Dimension</th>
      <th>Mobile App (Flutter)</th>
      <th>Web Dashboard (React / Vite)</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><strong>Primary Role</strong></td>
      <td>Shopper / In-the-field Consumer</td>
      <td>Operator / Household Accountant / Administrator</td>
    </tr>
    <tr>
      <td><strong>Key Workflow</strong></td>
      <td>Quick camera photo snap, crop, and upload</td>
      <td>Triage desk, spending analytics, deep audit ledger</td>
    </tr>
    <tr>
      <td><strong>Interaction Mode</strong></td>
      <td>One-thumb touch on smartphone</td>
      <td>Multi-column table, keyboard shortcuts, mouse hover</td>
    </tr>
    <tr>
      <td><strong>Data Density</strong></td>
      <td>Minimal (Automated capture)</td>
      <td>High Detail (Raw OCR verification, hashes, latency)</td>
    </tr>
  </tbody>
</table>

<h2>2. Desktop Viewport & Spatial Layout Blueprint</h2>
<p>The desktop dashboard is optimized for 1280px to 1920px+ viewports without unnecessary modal popups or hidden dropdowns. Below is the spatial architecture:</p>

<div class="wireframe-container">
  <div class="wireframe-header">
    <span>RECEIPTLEDGER DESKTOP CONSOLE [1280px+ Fixed-Fluid Workspace]</span>
    <span>STATUS: ALL ENGINES OPERATIONAL (GEMINI AI | CLOUD VISION | SUPABASE)</span>
  </div>
  
  <div class="wireframe-kpis">
    <div class="wireframe-kpi">
      <div class="wireframe-kpi-val">148 Receipts</div>
      <div class="wireframe-kpi-lbl">Total Ingested (+14%)</div>
    </div>
    <div class="wireframe-kpi">
      <div class="wireframe-kpi-val">PKR 184,250.00</div>
      <div class="wireframe-kpi-lbl">Total Reconciled Spend</div>
    </div>
    <div class="wireframe-kpi">
      <div class="wireframe-kpi-val" style="color: #DC2626;">7 Pending</div>
      <div class="wireframe-kpi-lbl">Human Review Queue</div>
    </div>
    <div class="wireframe-kpi">
      <div class="wireframe-kpi-val" style="color: #059669;">96.2%</div>
      <div class="wireframe-kpi-lbl">AI Extraction Accuracy</div>
    </div>
  </div>

  <div class="wireframe-split">
    <div class="wireframe-pane">
      <div class="wireframe-pane-title">WORKSPACE A: HUMAN-IN-THE-LOOP REVIEW DESK (50% Split)</div>
      <div style="font-size: 6.2pt; color: #475569;">
        • <strong>Left Canvas:</strong> Scaled receipt image viewer with interactive Pan & Zoom (100% - 400%) and glowing 2px bounding-box snippet highlight.<br/>
        • <strong>Right Triage Form:</strong> Item candidate name, quantity, unit price, total, and model confidence score pill.<br/>
        • <strong>Tactile Controls:</strong> [Confirm & Accept (Enter)] | [Save Edits (Ctrl+S)] | Auto-advances to next item.
      </div>
    </div>
    <div class="wireframe-pane">
      <div class="wireframe-pane-title">WORKSPACE B: INGESTION AUDIT LEDGER (50% Split)</div>
      <div style="font-size: 6.2pt; color: #475569;">
        • <strong>Search & Filter Bar:</strong> Jump with key '/' | Type Filter (Printed/Handwritten) | Date Range Picker.<br/>
        • <strong>High-Density Grid:</strong> Store name, date, item count, total spend, perceptual hash (pHash), OCR latency.<br/>
        • <strong>Slide-Out Drawer:</strong> Full receipt inspection, raw OCR payload, and duplicate comparison.
      </div>
    </div>
  </div>

  <div style="background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 2pt; padding: 4pt; font-size: 6.2pt; color: #334155;">
    <strong>BOTTOM TELEMETRY & ANALYTICS RIBBON:</strong> Category Spend Donut Chart | Monthly Spend Trajectory Velocity | Observability Benchmark Run Logs (/api/v1/system/runs)
  </div>
</div>

<div class="page-break"></div>

<h2>3. Self-Contained Visual References & Embedded Image Showcase</h2>
<p>All relevant receipt samples and existing screen states are <strong>embedded directly within this document</strong>. No searching through repository folders required.</p>

<div class="image-showcase">
  <div class="image-card">
    <img src="data:image/jpeg;base64,{b64_review_queue}" alt="Current Mobile Review Queue">
    <div class="image-title">Reference 1: Current Mobile Review Screen</div>
    <div class="image-desc">Shows existing barebones mobile review queue with raw technical exception. Replaced on desktop by our split-screen triage workspace.</div>
  </div>
  <div class="image-card">
    <img src="data:image/jpeg;base64,{b64_javed_nahari}" alt="Javed Nihari Restaurant POS">
    <div class="image-title">Reference 2: Real Pakistani POS Receipt</div>
    <div class="image-desc">Javed Nihari POS receipt with bilingual Urdu/English headers, itemized dishes, GST sales tax lines, and thermal fade.</div>
  </div>
  <div class="image-card">
    <img src="data:image/jpeg;base64,{b64_metro_safari}" alt="Metro Cash and Carry Retail">
    <div class="image-title">Reference 3: Retail Superstore Receipt</div>
    <div class="image-desc">Metro Cash & Carry receipt featuring high-density multi-column product codes, barcode numbers, and per-unit prices.</div>
  </div>
</div>

<h2>4. Receipt Ingestion, Deduplication & Verification Pipeline</h2>

<div class="flow-box">
[1. Upload Receipt Image] ──► [2. OpenCV Preprocessing & Deskew] ──► [3. Perceptual Hashing (Layer 1 & 2)]
                                                                               │
                                ┌──────────────────────────────────────────────┴──────────────────────────┐
                                ▼                                                                         ▼
                       Exact SHA256 OR pHash dist &le; 4                                             Unique Receipt
                                │                                                                         │
                                ▼                                                                         ▼
                       409 Conflict Banner                                                       [4. Gemini AI Vision]
                       (Link to existing receipt)                                                         │
                                                                                ┌─────────────────────────┴───────────────┐
                                                                                ▼                                         ▼
                                                                       Confidence &ge; 85%                       Confidence &lt; 85%
                                                                                │                                         │
                                                                                ▼                                         ▼
                                                                        status: PROCESSED                      status: PENDING_REVIEW
                                                                        (Direct to Ledger)                     (Added to Review Queue)
                                                                                                                          │
                                                                                                                          ▼
                                                                                                               [5. Desktop Review Desk]
                                                                                                               1-Click [Enter] / [Ctrl+S]
</div>

<h2>5. Desktop Keyboard Ergonomics & Shortcuts Cheat Sheet</h2>

<table>
  <thead>
    <tr>
      <th>Shortcut</th>
      <th>Context</th>
      <th>Action / Result</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><code>Enter</code> / <code>Return</code></td>
      <td>Review Desk Table</td>
      <td>1-Click Approve active item (<code>action: "ACCEPTED"</code>) and auto-focus next row</td>
    </tr>
    <tr>
      <td><code>Ctrl + S</code> / <code>Cmd + S</code></td>
      <td>Review Desk Table</td>
      <td>Save inline edits on candidate name, qty, or price (<code>action: "EDITED"</code>)</td>
    </tr>
    <tr>
      <td><code>Tab</code></td>
      <td>Review Desk Row</td>
      <td>Advance focus between candidate item name, quantity, unit, and price fields</td>
    </tr>
    <tr>
      <td><code>Shift + Tab</code></td>
      <td>Review Desk Row</td>
      <td>Move backward to previous field</td>
    </tr>
    <tr>
      <td><code>&uarr;</code> / <code>&darr;</code> or <code>J</code> / <code>K</code></td>
      <td>Audit Ledger Grid</td>
      <td>Select previous / next receipt row</td>
    </tr>
    <tr>
      <td><code>Space</code></td>
      <td>Audit Ledger Row</td>
      <td>Open Slide-Out Inspector Drawer for selected receipt</td>
    </tr>
    <tr>
      <td><code>Esc</code></td>
      <td>Modal / Drawer</td>
      <td>Dismiss Slide-Out Inspector Drawer or cancel inline editing</td>
    </tr>
    <tr>
      <td><code>/</code> (Forward Slash)</td>
      <td>Global</td>
      <td>Jump focus directly to Ingestion Ledger Search input</td>
    </tr>
  </tbody>
</table>

<div class="page-break"></div>

<h2>6. Backend API Directory & Concrete JSON Payloads</h2>

<table>
  <thead>
    <tr>
      <th>Method</th>
      <th>Endpoint</th>
      <th>Primary Purpose</th>
      <th>Key Query / Body Params</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><code>GET</code></td>
      <td><code>/api/v1/health</code></td>
      <td>System health & engine quota</td>
      <td>None (Returns Gemini & Cloud Vision status)</td>
    </tr>
    <tr>
      <td><code>GET</code></td>
      <td><code>/api/v1/dashboard/overview</code></td>
      <td>Monthly spend, KPIs & category split</td>
      <td><code>year=2026&amp;month=10</code></td>
    </tr>
    <tr>
      <td><code>GET</code></td>
      <td><code>/api/v1/review-queue</code></td>
      <td>Unresolved low-confidence items</td>
      <td><code>status_filter=UNRESOLVED</code></td>
    </tr>
    <tr>
      <td><code>PATCH</code></td>
      <td><code>/api/v1/review-queue/{{id}}</code></td>
      <td>1-click accept or inline edit</td>
      <td><code>confirmed_name</code>, <code>action</code></td>
    </tr>
    <tr>
      <td><code>GET</code></td>
      <td><code>/api/v1/analytics/receipts</code></td>
      <td>Searchable paginated audit ledger</td>
      <td><code>page=1&amp;page_size=25&amp;search=Imtiaz</code></td>
    </tr>
    <tr>
      <td><code>GET</code></td>
      <td><code>/api/v1/system/runs</code></td>
      <td>Observability & benchmark logs</td>
      <td>None (Returns run IDs and accuracy %)</td>
    </tr>
  </tbody>
</table>

<h3>6.1 System Health (GET /api/v1/health)</h3>
<div class="code-json">{{
  "status": "ok",
  "version": "1.0.0",
  "environment": "development",
  "engines": {{
    "cloud_vision": "ok (quota_remaining=950)",
    "tesseract": "ok",
    "easyocr": "ok (lazy-loaded)",
    "gemini": "ok (model=gemini-3.5-flash-lite)",
    "database": "supabase"
  }}
}}</div>

<h3>6.2 Review Queue Triage Item (GET /api/v1/review-queue)</h3>
<div class="code-json">[
  {{
    "queue_id": "7a79f40f-3047-4d76-a577-a41a58af9a56",
    "line_item_id": "93b118b5-12ea-44d5-8bc2-a5d6f1406541",
    "receipt_id": "41fd8d2a-e322-4f5f-aa37-ed65ffab5519",
    "merchant_name": "Chaudhry Sabzi & Fruit Store",
    "raw_text": "129728 WITHA PER KG 0.640",
    "candidate_name": "Sweet Melon",
    "model_confidence": 0.745,
    "review_status": "UNRESOLVED"
  }}
]</div>

<h3>6.3 Resolving Item (PATCH /api/v1/review-queue/{{queue_id}})</h3>
<div class="code-json">// 1-Click Accept:
{{ "confirmed_name": "Sweet Melon", "action": "ACCEPTED" }}

// Inline Edit & Correct:
{{ "confirmed_name": "Sweet Melon", "confirmed_quantity": 0.64, "confirmed_unit_price": 199.0, "action": "EDITED" }}</div>

<h2>7. Design Aesthetic, Constraints & Testing Controls</h2>
<ul>
  <li><strong>Rule #1: ZERO GRADIENTS.</strong> No rainbow fills or shiny button gradients. Use solid colors with clean contrast.</li>
  <li><strong>Rule #2: ZERO GLASSMORPHISM.</strong> No liquid acrylic blur (<code>backdrop-filter: blur</code>). Use clean 1px borders (<code>#CBD5E1</code>) and crisp white/slate cards.</li>
  <li><strong>Instant Test Controls:</strong> Click <code>[Seed Demo Data]</code> (<code>POST /api/v1/dashboard/seed-demo</code>) to load 148 realistic receipts. Click <code>[Reset Ledger]</code> (<code>POST /api/v1/dashboard/reset</code>) to test zero-data states.</li>
  <li><strong>Default Admin Credentials:</strong> <code>user@receiptledger.com</code> / <code>demo1234</code>.</li>
</ul>

</body>
</html>
"""

# Write printable HTML
out_html = docs_dir / "ReceiptLedger_Dashboard_Design_Brief_PRINTABLE.html"
out_html.write_text(html_content, encoding="utf-8")
print("Wrote printable HTML successfully")

# Compile to PDF using Chrome or Edge headless
pdf_out = docs_dir / "ReceiptLedger_Dashboard_Design_Brief.pdf"
chrome_paths = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]

browser_exe = None
for cp in chrome_paths:
    if Path(cp).exists():
        browser_exe = cp
        break

if browser_exe:
    cmd = [
        browser_exe,
        "--headless",
        "--disable-gpu",
        "--no-pdf-header-footer",
        f"--print-to-pdf={pdf_out.resolve()}",
        str(out_html.resolve()),
    ]
    print("Compiling enriched PDF with:", browser_exe)
    res = subprocess.run(cmd, capture_output=True, text=True)
    if pdf_out.exists():
        print(f"SUCCESS! Dashboard PDF created at: {pdf_out.resolve()} ({pdf_out.stat().st_size / 1024:.1f} KB)")
    else:
        print("PDF command output:", res.stdout, res.stderr)
else:
    print("No headless browser found.")

# Clean up temporary printable HTML file so repo stays clean
if out_html.exists():
    out_html.unlink()
    print("Cleaned up temporary HTML file:", out_html.name)
