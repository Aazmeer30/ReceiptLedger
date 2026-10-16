import base64
import subprocess
from pathlib import Path

docs_dir = Path(__file__).resolve().parent
screenshots_dir = docs_dir / "assets" / "barebones_screenshots"

def get_b64(filename):
    p = screenshots_dir / filename
    if p.exists():
        return "data:image/jpeg;base64," + base64.b64encode(p.read_bytes()).decode("ascii")
    return ""

img_settings = get_b64("01_settings_screen_barebones.jpg")
img_capture  = get_b64("02_capture_screen_barebones.jpg")
img_ledger   = get_b64("03_ledger_screen_barebones.jpg")
img_review   = get_b64("04_review_queue_barebones.jpg")

html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>ReceiptLedger – Master UI/UX Design Brief & Specification</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');
  
  @page {{
    size: A4 portrait;
    margin: 16mm 14mm 16mm 14mm;
  }}

  body {{
    font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    color: #111827;
    background: #FFFFFF;
    line-height: 1.5;
    font-size: 9.5pt;
    margin: 0;
    padding: 0;
  }}

  h1, h2, h3, h4 {{
    color: #0F172A;
    font-weight: 700;
    page-break-after: avoid;
  }}

  h1 {{
    font-size: 22pt;
    margin-top: 0;
    margin-bottom: 2pt;
    letter-spacing: -0.5px;
  }}

  .subtitle {{
    font-size: 11pt;
    color: #475569;
    margin-bottom: 12pt;
    border-bottom: 2px solid #E2E8F0;
    padding-bottom: 6pt;
  }}

  .badge-row {{
    margin-bottom: 12pt;
  }}

  .badge {{
    display: inline-block;
    padding: 3pt 7pt;
    font-size: 8pt;
    font-weight: 600;
    border-radius: 4pt;
    margin-right: 5pt;
    background: #F1F5F9;
    color: #334155;
    border: 1px solid #CBD5E1;
  }}

  .badge-primary {{
    background: #0F172A;
    color: #FFFFFF;
    border-color: #0F172A;
  }}

  .alert-box {{
    background: #FEF3C7;
    border: 1.5px solid #F59E0B;
    border-radius: 6pt;
    padding: 9pt 11pt;
    margin: 10pt 0;
    page-break-inside: avoid;
  }}

  .alert-title {{
    font-weight: 700;
    color: #92400E;
    font-size: 9.5pt;
    margin-bottom: 2pt;
  }}

  .alert-box p {{
    margin: 0;
    color: #78350F;
    font-size: 8.5pt;
  }}

  .rule-card {{
    background: #F8FAFC;
    border: 1.5px solid #0F172A;
    border-radius: 6pt;
    padding: 9pt 11pt;
    margin-bottom: 8pt;
    page-break-inside: avoid;
  }}

  .rule-title {{
    font-weight: 800;
    font-size: 9.5pt;
    color: #0F172A;
    margin-bottom: 2pt;
  }}

  table {{
    width: 100%;
    border-collapse: collapse;
    margin: 8pt 0 12pt 0;
    font-size: 8.5pt;
    page-break-inside: avoid;
  }}

  th, td {{
    padding: 5pt 7pt;
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

  .screen-review-container {{
    display: flex;
    gap: 12pt;
    margin: 10pt 0 14pt 0;
    page-break-inside: avoid;
    align-items: flex-start;
  }}

  .screen-img-box {{
    flex: 0 0 145pt;
    border: 1.5px solid #CBD5E1;
    border-radius: 6pt;
    padding: 4pt;
    background: #F8FAFC;
    text-align: center;
  }}

  .screen-img-box img {{
    width: 100%;
    border-radius: 4pt;
    display: block;
  }}

  .screen-img-caption {{
    font-size: 7pt;
    color: #64748B;
    margin-top: 3pt;
    font-weight: 600;
  }}

  .screen-text-box {{
    flex: 1;
  }}

  .screen-text-box h3 {{
    margin-top: 0;
    font-size: 10.5pt;
    color: #0F172A;
    margin-bottom: 4pt;
  }}

  .critique-box {{
    background: #FEF2F2;
    border-left: 3px solid #EF4444;
    padding: 5pt 7pt;
    font-size: 8pt;
    color: #991B1B;
    margin-bottom: 5pt;
  }}

  .wishlist-box {{
    background: #F0FDF4;
    border-left: 3px solid #22C55E;
    padding: 5pt 7pt;
    font-size: 8pt;
    color: #166534;
  }}

  .wishlist-box ul, .critique-box ul {{
    margin: 0;
    padding-left: 12pt;
  }}

  .code-block {{
    background: #0F172A;
    color: #F8FAFC;
    padding: 7pt 9pt;
    border-radius: 5pt;
    font-family: 'JetBrains Mono', monospace;
    font-size: 7.5pt;
    line-height: 1.35;
    white-space: pre-wrap;
    word-break: break-word;
    margin: 5pt 0 10pt 0;
    page-break-inside: avoid;
  }}

  .page-break {{
    page-break-before: always;
  }}
</style>
</head>
<body>

<h1>ReceiptLedger</h1>
<div class="subtitle">Mobile UI/UX Master Design Brief & Google Stitch Prompt Guide</div>

<div class="badge-row">
  <span class="badge badge-primary">Target: Flutter iOS & Android</span>
  <span class="badge">Tool: Google Stitch & Figma</span>
  <span class="badge">Output: Images / Mockups Only (No Code)</span>
  <span class="badge">Style: Minimal Flat (No Gradients)</span>
</div>

<div class="alert-box">
  <div class="alert-title">Clarification on "Warmth":</div>
  <p>When we say warm, we do <strong>NOT</strong> mean yellowish or beige colors. <strong>We mean human, approachable, friendly, and effortless to use.</strong> Clean layouts that feel like a trusty personal pocket notebook rather than an intimidating corporate tax audit software or spreadsheet.</p>
</div>

<div class="rule-card">
  <div class="rule-title">RULE #1: ABSOLUTELY ZERO GRADIENTS</div>
  <p style="margin:0; font-size:8.5pt; color:#334155;">Use pure, solid, deliberate flat colors. No color fades, multi-stop gradients, or glossy button highlights.</p>
</div>

<div class="rule-card">
  <div class="rule-title">RULE #2: ZERO LIQUID GLASS / GLASSMORPHISM</div>
  <p style="margin:0; font-size:8.5pt; color:#334155;">No translucent floating frosted-glass cards, blur filters, or skeuomorphic plastic reflections. Use clean flat surfaces with crisp 1px to 1.5px outlines.</p>
</div>

<h2>1. Deliverable #1: App Icon & Brand Logo (Top Priority)</h2>
<p>The app icon will sit on user homescreens every day. It must be unique, memorable, and fun.</p>
<ul>
  <li><strong>Tone:</strong> Casual, playful, engaging, and minimal. Avoid stiff calculators, boring folders, or dry tax icons.</li>
  <li><strong>Motif Concepts:</strong> A folded receipt paper slip with a friendly smile notch, a smiling tally mark, or an origami-like minimal paper roll.</li>
  <li><strong>Homescreen Impact:</strong> High contrast, vector flat, instantly recognizable at 32x32px on any wallpaper, and stunning at 1024x1024px.</li>
</ul>

<h2>2. Deliverable #2: Secret Tucked-Away Profile Sidebar (Drawer)</h2>
<p>Keep the main screen clean by tucking profile and settings into a sleek slide-out drawer:</p>
<ul>
  <li><strong>Trigger:</strong> Slides out smoothly when the user taps their <strong>circular avatar</strong> in the top-right corner of the app bar.</li>
  <li><strong>User Profile Header:</strong> Avatar photo, full name (<em>Asad Khan</em>), email (<em>user@receiptledger.com</em>), and a clean status badge (<em>Pro / Local Ledger</em>).</li>
  <li><strong>Menu Options:</strong> Profile Settings, Export Ledger (CSV/PDF), Theme Selector (Light / Dark / High-Contrast B&W), and About ReceiptLedger (version & licenses).</li>
  <li><strong>Log Out:</strong> Distinct clean logout button with a subtle red accent at the very bottom of the drawer.</li>
</ul>

<div class="page-break"></div>

<h2>3. Current Barebones Screens & Critique (What Needs Improvement)</h2>
<p>Here are the real screenshots of the current working Flutter application. Use these as functional blueprints to redesign into modern, high-fidelity mockups:</p>

<div class="screen-review-container">
  <div class="screen-img-box">
    <img src="{img_capture}" alt="Current Capture Screen" />
    <div class="screen-img-caption">Screen 1: Receipt Capture</div>
  </div>
  <div class="screen-text-box">
    <h3>1. Receipt Capture & Scan Screen</h3>
    <div class="critique-box">
      <strong>What's Wrong Currently:</strong>
      <ul>
        <li>Two tiny disconnected buttons ('Take Photo' & 'Gallery') float awkwardly at the top.</li>
        <li>An unappealing empty gray placeholder box in the center.</li>
        <li>The 'Upload & Process Receipt' button is a dead gray slab at the bottom.</li>
      </ul>
    </div>
    <div class="wishlist-box">
      <strong>Redesign Wishlist:</strong>
      <ul>
        <li>Prominent, inviting camera viewfinder card with receipt corner framing marks.</li>
        <li>Pill switch toggle for [Single Receipt | Batch Scan Mode].</li>
        <li>Large tactile shutter button for camera, plus quick gallery picker.</li>
        <li>Subtle status badge showing active engine: <em>Gemini AI Vision (Fast)</em>.</li>
        <li>Recent scan quick-preview thumbnail card at the bottom.</li>
      </ul>
    </div>
  </div>
</div>

<div class="screen-review-container">
  <div class="screen-img-box">
    <img src="{img_review}" alt="Current Review Queue Screen" />
    <div class="screen-img-caption">Screen 2: Review Queue</div>
  </div>
  <div class="screen-text-box">
    <h3>2. Review Queue Screen (Human-in-the-Loop)</h3>
    <div class="critique-box">
      <strong>What's Wrong Currently:</strong>
      <ul>
        <li>A terrifying technical error message is dumped in raw red text when timeout occurs: <em>TimeoutException after 0:00:10.000000</em>.</li>
        <li>No side-by-side verification; items are crammed into a raw list.</li>
      </ul>
    </div>
    <div class="wishlist-box">
      <strong>Redesign Wishlist:</strong>
      <ul>
        <li>Verification Card pairing a cropped snippet of physical receipt paper with editable candidate text fields (Item Name, Qty, Price).</li>
        <li>Confidence pill indicator (e.g. <em>74% Match - Check Price</em>).</li>
        <li>One-tap solid green [Confirm] and outlined [Edit] buttons.</li>
        <li>Friendly error state replacing raw technical dumps with an illustrative card and a simple [Retry Connection] button.</li>
      </ul>
    </div>
  </div>
</div>

<div class="page-break"></div>

<div class="screen-review-container">
  <div class="screen-img-box">
    <img src="{img_ledger}" alt="Current Ledger Screen" />
    <div class="screen-img-caption">Screen 3: Receipt Ledger</div>
  </div>
  <div class="screen-text-box">
    <h3>3. Ledger & Spending Intelligence Screen</h3>
    <div class="critique-box">
      <strong>What's Wrong Currently:</strong>
      <ul>
        <li>A blank screen with a solitary spinning circle.</li>
        <li>No monthly selector, no category pills, and no item search bar.</li>
      </ul>
    </div>
    <div class="wishlist-box">
      <strong>Redesign Wishlist:</strong>
      <ul>
        <li>Monthly Spend Total banner (e.g., <em>Rs. 42,850</em> with month picker dropdown).</li>
        <li>Horizontal filter pills for categories (<em>All, Groceries, Pharmacy, Snacks, Utilities</em>).</li>
        <li>Clean receipt row cards (Merchant name, Date, Item Count, Total Price).</li>
        <li>Minimal search bar to instantly find items (e.g., 'Atta', 'Panadol').</li>
      </ul>
    </div>
  </div>
</div>

<div class="screen-review-container">
  <div class="screen-img-box">
    <img src="{img_settings}" alt="Current Settings Screen" />
    <div class="screen-img-caption">Screen 4: Settings & Backend</div>
  </div>
  <div class="screen-text-box">
    <h3>4. Backend & Engine Settings Screen</h3>
    <div class="critique-box">
      <strong>What's Wrong Currently:</strong>
      <ul>
        <li>Looks like a developer debug screen with raw IP addresses, red timeout exceptions, and raw inputs.</li>
      </ul>
    </div>
    <div class="wishlist-box">
      <strong>Redesign Wishlist:</strong>
      <ul>
        <li>Clean status dot: Green <em>Connected to Gemini Vision</em> or Amber <em>Offline Mode</em>.</li>
        <li>Clean toggle pills for presets: [Local PC Wi-Fi | Cloud Backend | Demo Mode].</li>
        <li>Overview stats card: Total receipts saved, total spend recorded, and storage usage.</li>
      </ul>
    </div>
  </div>
</div>

<h2>4. Multiple Theming Options (Including High-Contrast B&W)</h2>
<table>
  <thead>
    <tr>
      <th>Theme Name</th>
      <th>Background</th>
      <th>Primary Accent</th>
      <th>Text / Details</th>
      <th>Vibe & Mood</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><strong>Stark Black & White</strong></td>
      <td>#FFFFFF (Pure White)</td>
      <td>#000000 (Solid Pitch Black)</td>
      <td>#000000 (1.5px Black Borders)</td>
      <td>Editorial, Swiss minimal, high contrast, zero distractions.</td>
    </tr>
    <tr>
      <td><strong>OLED Pitch Dark</strong></td>
      <td>#000000 (True Black)</td>
      <td>#FFFFFF (Solid White Pills)</td>
      <td>#E5E7EB (Crisp White Text)</td>
      <td>Sleek, stealthy, battery-saving dark mode.</td>
    </tr>
    <tr>
      <td><strong>Modern Sage & Slate</strong></td>
      <td>#F9FAF9 (Soft Clean Paper)</td>
      <td>#1E4D38 (Deep Forest Sage)</td>
      <td>#111827 (Charcoal Slate)</td>
      <td>Fresh, calm, organized, market & grocery feel.</td>
    </tr>
    <tr>
      <td><strong>Contrast Navy & Amber</strong></td>
      <td>#F4F6F8 (Cool Parchment)</td>
      <td>#0F172A (Midnight Navy)</td>
      <td>#F59E0B (Safety Amber Pop)</td>
      <td>Sharp, high clarity, trustworthy modern fintech feel.</td>
    </tr>
  </tbody>
</table>

<h2>5. Micro-Interactions & Feedback Toasts</h2>
<ul>
  <li><strong>Success Toast:</strong> Solid green pill + <em>"Receipt processed! 5 items added to Groceries."</em></li>
  <li><strong>Error Toast:</strong> Solid red pill + <em>"Connection timed out. Saved locally for offline sync."</em> with a flat <em>[Retry]</em> tap target.</li>
  <li><strong>Warning Toast:</strong> Solid amber pill + <em>"2 items need confirmation in Review Queue."</em></li>
  <li><strong>Skeleton Shimmers:</strong> Smooth pulsing bone rectangles while loading instead of blank spinning wheels.</li>
</ul>

<h2>6. Ready-to-Use Google Stitch Prompts</h2>
<p>Copy and paste these exact prompts directly into Google Stitch:</p>

<div class="code-block"># Prompt 1: Homescreen App Icon
Design a modern, minimalist mobile application icon for "ReceiptLedger", an expense tracker for paper receipts.
Style: Playful, casual, friendly, approachably modern.
Visual motif: A clean, stylized paper receipt slip with a subtle smile fold or geometric notch.
Strict constraints: Completely flat vector, ZERO gradients, ZERO 3D glossy effects, solid colors only.
Palette: Crisp white background, solid deep black line art, and a single accent pop of warm amber or sage green.
Needs high contrast, instantly memorable on an iPhone or Android homescreen.</div>

<div class="code-block"># Prompt 2: Secret Profile Drawer (Sidebar)
Design a sleek, functional mobile slide-out drawer (sidebar) for a receipt ledger app.
Trigger: Slides out when tapping the circular profile avatar in the top app bar.
Contents:
- Top: Circular user photo, name "Asad Khan", email "user@receiptledger.com", and a small "Pro Ledger" tag.
- Menu items with clean outline icons: Profile Settings, Export Data (CSV/PDF), App Licenses & About.
- Theme Switcher: A clean 3-way flat pill switch for [Light | Dark | B&W].
- Bottom: Distinct Logout button with clean flat red outline.
Aesthetic: Minimalist, clean flat cards, zero gradients, zero glass blur.</div>

<div class="code-block"># Prompt 3: High-Contrast Black & White Mobile Redesign
Redesign a receipt scanner mobile application in high-contrast stark black and white aesthetic.
Inspired by minimalist Swiss editorial design and Japanese stationery.
Screens to show:
1. Receipt Capture View: Clean camera viewfinder with corner alignment marks, pill toggle for [Single | Batch], and a solid black shutter button.
2. Review Queue: A card displaying a cropped photo snippet of receipt text, paired with editable candidate text fields for item name and price, with solid black [Confirm] button and outline [Edit] button.
3. Floating Toast: A clean black pill banner showing "Receipt saved to ledger (PKR 2,400)".
Strict rules: 100% flat vector, zero gradients, zero shadows, zero liquid glass. Crisp 1.5px black borders.</div>

</body>
</html>
"""

out_html = docs_dir / "DESIGN_BRIEF_PRINTABLE.html"
out_html.write_text(html_content, encoding="utf-8")
print("HTML generated successfully at:", out_html)

# Now compile to PDF using Edge or Chrome headless
pdf_out = docs_dir / "ReceiptLedger_UI_UX_Design_Brief.pdf"
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
    print("Compiling PDF with:", browser_exe)
    res = subprocess.run(cmd, capture_output=True, text=True)
    if pdf_out.exists():
        print(f"SUCCESS! PDF created at: {pdf_out.resolve()} ({pdf_out.stat().st_size / 1024:.1f} KB)")
    else:
        print("PDF command output:", res.stdout, res.stderr)
else:
    print("No headless browser found.")

# Clean up temporary printable HTML file so repo stays clean
if out_html.exists():
    out_html.unlink()
    print("Cleaned up temporary HTML file:", out_html.name)

