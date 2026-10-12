"""
ReceiptLedger - Generator for Diverse & Challenging Benchmark Receipts
======================================================================
Synthesizes 4 photorealistic, diverse, and challenging Pakistani receipts:
  1. challenging_pharmacy_receipt.jpg     - Tilted thermal pharmacy receipt on clinic counter with horizontal creases
  2. challenging_carbon_copy_karyana.jpg  - Tinted duplicate carbon bill with harsh diagonal overhead camera shadow
  3. challenging_greengrocer_marble.jpg   - Hand-written produce memo rotated on kitchen marble counter
  4. challenging_pos_creased_roll.jpg     - Long narrow cash roll receipt with vertical fold crease & barcode
"""

import os, math, random
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont, ImageFilter

OUTPUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "sample_receipts"))
os.makedirs(OUTPUT_DIR, exist_ok=True)

FONTS_DIR = r"C:\Windows\Fonts"

def get_font(name: str, size: int):
    path = os.path.join(FONTS_DIR, name)
    if os.path.exists(path):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


# ── 1. Pharmacy Thermal Receipt (Fazal Din & Sons Chemists) ───────────────────
def generate_pharmacy_receipt():
    w_slip, h_slip = 540, 960
    slip = Image.new("RGBA", (w_slip, h_slip), (248, 248, 246, 255))
    draw = ImageDraw.Draw(slip)

    # Slight thermal paper texture
    arr = np.array(slip)
    noise = np.random.normal(0, 4, arr.shape[:2]).astype(np.int16)
    for c in range(3):
        arr[:, :, c] = np.clip(arr[:, :, c].astype(np.int16) + noise, 0, 255).astype(np.uint8)
    slip = Image.fromarray(arr, "RGBA")
    draw = ImageDraw.Draw(slip)

    f_head = get_font("courbd.ttf", 26)
    f_sub = get_font("cour.ttf", 18)
    f_body = get_font("cour.ttf", 20)
    f_bold = get_font("courbd.ttf", 22)

    # Header
    draw.text((270, 40), "FAZAL DIN & SONS CHEMISTS", fill=(30, 30, 30), font=f_head, anchor="mm")
    draw.text((270, 75), "Branch: Mall Road, Lahore", fill=(50, 50, 50), font=f_sub, anchor="mm")
    draw.text((270, 100), "Tel: 042-37351234  NTN: 1234567-8", fill=(60, 60, 60), font=f_sub, anchor="mm")
    draw.text((270, 125), "Date: 12/10/2026   Time: 14:32", fill=(40, 40, 40), font=f_sub, anchor="mm")
    draw.line([(30, 150), (510, 150)], fill=(80, 80, 80), width=2)

    # Column header
    draw.text((35, 165), "ITEM DESCRIPTION", fill=(30, 30, 30), font=f_bold)
    draw.text((360, 165), "QTY", fill=(30, 30, 30), font=f_bold)
    draw.text((440, 165), "AMOUNT", fill=(30, 30, 30), font=f_bold)
    draw.line([(30, 195), (510, 195)], fill=(120, 120, 120), width=1)

    # Line items
    items = [
        ("Panadol Extra", "2 pkt", "340.00"),
        ("Disprin 300mg", "1 pkt", "120.00"),
        ("Sancos Syrup", "1 bot", "280.00"),
        ("Dettol Antiseptic", "1 bot", "310.00"),
        ("Surgical Mask", "1 pkt", "250.00"),
    ]

    y = 215
    for name, qty, amt in items:
        draw.text((35, y), name, fill=(25, 25, 25), font=f_body)
        draw.text((360, y), qty, fill=(25, 25, 25), font=f_body)
        draw.text((505, y), amt, fill=(25, 25, 25), font=f_body, anchor="ra")
        y += 45

    draw.line([(30, y + 10), (510, y + 10)], fill=(80, 80, 80), width=2)
    y += 30

    # Summary
    draw.text((35, y), "SUBTOTAL:", fill=(40, 40, 40), font=f_body)
    draw.text((505, y), "Rs. 1300.00", fill=(40, 40, 40), font=f_body, anchor="ra")
    y += 35
    draw.text((35, y), "TOTAL AMOUNT:", fill=(10, 10, 10), font=f_bold)
    draw.text((505, y), "Rs. 1300.00", fill=(10, 10, 10), font=f_bold, anchor="ra")
    y += 35
    draw.text((35, y), "CASH PAID:", fill=(40, 40, 40), font=f_body)
    draw.text((505, y), "Rs. 1500.00", fill=(40, 40, 40), font=f_body, anchor="ra")
    y += 35
    draw.text((35, y), "CHANGE:", fill=(40, 40, 40), font=f_body)
    draw.text((505, y), "Rs.  200.00", fill=(40, 40, 40), font=f_body, anchor="ra")
    y += 45

    draw.line([(30, y), (510, y)], fill=(120, 120, 120), width=1)
    y += 20
    draw.text((270, y), "* THANK YOU - GET WELL SOON *", fill=(70, 70, 70), font=f_sub, anchor="mm")

    # Horizontal crease artifact
    crease_y = 480
    crease_overlay = Image.new("RGBA", (w_slip, h_slip), (0, 0, 0, 0))
    c_draw = ImageDraw.Draw(crease_overlay)
    c_draw.line([(0, crease_y), (w_slip, crease_y)], fill=(30, 30, 30, 60), width=3)
    c_draw.line([(0, crease_y + 3), (w_slip, crease_y + 3)], fill=(255, 255, 255, 75), width=2)
    crease_overlay = crease_overlay.filter(ImageFilter.GaussianBlur(1.5))
    slip = Image.alpha_composite(slip, crease_overlay)

    # Composite onto clinic laminate counter
    bg_w, bg_h = 950, 1400
    bg = Image.new("RGBA", (bg_w, bg_h), (52, 60, 68, 255))
    # Add subtle laminate pattern
    bg_arr = np.array(bg)
    bg_noise = np.random.normal(0, 6, bg_arr.shape[:2]).astype(np.int16)
    for c in range(3):
        bg_arr[:, :, c] = np.clip(bg_arr[:, :, c].astype(np.int16) + bg_noise, 0, 255).astype(np.uint8)
    bg = Image.fromarray(bg_arr, "RGBA")

    # Rotate slip by 7 degrees
    rotated_slip = slip.rotate(7, resample=Image.BICUBIC, expand=True)

    # Shadow
    shadow = Image.new("RGBA", rotated_slip.size, (0, 0, 0, 110))
    shadow.putalpha(rotated_slip.split()[3].point(lambda a: 110 if a > 0 else 0))
    shadow = shadow.filter(ImageFilter.GaussianBlur(12))

    cx = (bg_w - rotated_slip.width) // 2
    cy = (bg_h - rotated_slip.height) // 2
    bg.paste(shadow, (cx + 12, cy + 18), shadow)
    bg.paste(rotated_slip, (cx, cy), rotated_slip)

    out_path = os.path.join(OUTPUT_DIR, "challenging_pharmacy_receipt.jpg")
    bg.convert("RGB").save(out_path, quality=92)
    print("Generated:", out_path)


# ── 2. Carbon-Copy Karyana Bill with Harsh Overhead Diagonal Shadow ───────────
def generate_carbon_copy_karyana():
    w_slip, h_slip = 600, 980
    # Tinted duplicate pink/yellow memo paper
    slip = Image.new("RGBA", (w_slip, h_slip), (252, 245, 218, 255))
    draw = ImageDraw.Draw(slip)

    # Ruled lines
    for line_y in range(180, 880, 65):
        draw.line([(35, line_y), (565, line_y)], fill=(200, 220, 235), width=1)

    # Margin line
    draw.line([(100, 180), (100, 860)], fill=(240, 190, 190), width=1)
    draw.line([(450, 180), (450, 860)], fill=(240, 190, 190), width=1)

    f_urdu = get_font("tahoma.ttf", 26)
    f_eng_head = get_font("arialbd.ttf", 24)
    f_hand = get_font("comic.ttf", 24)
    f_sub = get_font("arial.ttf", 17)

    # Red printed header banner
    draw.text((300, 45), "سبحان اللہ کریانہ سٹور", fill=(190, 30, 30), font=f_urdu, anchor="mm")
    draw.text((300, 85), "Subhan Allah Karyana Store", fill=(190, 30, 30), font=f_eng_head, anchor="mm")
    draw.text((300, 118), "Prop: Haji Subhan • Cell: 0300-1234567", fill=(100, 50, 50), font=f_sub, anchor="mm")
    draw.text((300, 145), "Date: 11/10/26", fill=(30, 30, 80), font=f_hand, anchor="mm")
    draw.line([(35, 175), (565, 175)], fill=(190, 30, 30), width=2)

    # Handwritten items in blue ballpoint pen
    ink_color = (25, 45, 130)
    items = [
        ("Daal Mash 1kg", "540"),
        ("Surf Excel 500g", "310"),
        ("Tapal Danedar 200g", "380"),
        ("Lifebuoy Soap 3 pcs", "330"),
        ("Cooking Oil 2L", "1040"),
    ]

    y = 220
    for name, price in items:
        draw.text((115, y), name, fill=ink_color, font=f_hand)
        draw.text((540, y), price, fill=ink_color, font=f_hand, anchor="ra")
        y += 65

    # Hand-drawn circled total
    draw.text((300, 680), "Total = 2600 = ٹوٹل", fill=ink_color, font=f_urdu, anchor="mm")
    # Draw natural oval around total
    bbox = [110, 645, 490, 715]
    draw.ellipse(bbox, outline=(20, 40, 140), width=3)

    # Harsh diagonal shadow across the bottom half (simulates phone/hand shadow)
    shadow_mask = np.ones((h_slip, w_slip), dtype=np.float32)
    for r in range(h_slip):
        for c in range(w_slip):
            # Diagonal gradient from top-right to bottom-left
            proj = (r * 0.8 + c * 0.6) / (h_slip + w_slip)
            if proj > 0.45:
                factor = 1.0 - min(0.48, (proj - 0.45) * 1.5)
                shadow_mask[r, c] = factor

    slip_arr = np.array(slip).astype(np.float32)
    for c in range(3):
        slip_arr[:, :, c] *= shadow_mask
    slip = Image.fromarray(np.clip(slip_arr, 0, 255).astype(np.uint8), "RGBA")

    # Wood background
    bg_w, bg_h = 950, 1400
    bg = Image.new("RGBA", (bg_w, bg_h), (95, 65, 42, 255))
    # Wood grain simulation
    bg_arr = np.array(bg)
    y_idx = np.arange(bg_h)[:, None]
    grain = (np.sin(y_idx / 8.0) * 15 + np.random.normal(0, 8, (bg_h, bg_w))).astype(np.int16)
    for c in range(3):
        bg_arr[:, :, c] = np.clip(bg_arr[:, :, c].astype(np.int16) + grain, 0, 255).astype(np.uint8)
    bg = Image.fromarray(bg_arr, "RGBA")

    # Rotate slip slightly (-4 degrees)
    rotated_slip = slip.rotate(-4, resample=Image.BICUBIC, expand=True)

    shadow = Image.new("RGBA", rotated_slip.size, (0, 0, 0, 120))
    shadow.putalpha(rotated_slip.split()[3].point(lambda a: 120 if a > 0 else 0))
    shadow = shadow.filter(ImageFilter.GaussianBlur(10))

    cx = (bg_w - rotated_slip.width) // 2
    cy = (bg_h - rotated_slip.height) // 2
    bg.paste(shadow, (cx + 8, cy + 14), shadow)
    bg.paste(rotated_slip, (cx, cy), rotated_slip)

    out_path = os.path.join(OUTPUT_DIR, "challenging_carbon_copy_karyana.jpg")
    bg.convert("RGB").save(out_path, quality=92)
    print("Generated:", out_path)


# ── 3. Greengrocer Produce Slip on Kitchen Marble Counter (Tilt 18°) ───────────
def generate_greengrocer_marble():
    w_slip, h_slip = 560, 920
    slip = Image.new("RGBA", (w_slip, h_slip), (250, 250, 250, 255))
    draw = ImageDraw.Draw(slip)

    # Perforated notepad holes at top
    for hx in range(40, w_slip - 30, 50):
        draw.ellipse([hx, 15, hx + 16, 31], fill=(160, 160, 160, 255))

    f_urdu = get_font("tahoma.ttf", 25)
    f_eng_head = get_font("segoeuib.ttf", 24)
    f_hand = get_font("comic.ttf", 24)
    f_date = get_font("segoeui.ttf", 20)

    # Header
    draw.text((280, 65), "چوہدری سبزی اینڈ فروٹ شاپ", fill=(30, 80, 40), font=f_urdu, anchor="mm")
    draw.text((280, 105), "Chaudhry Sabzi & Fruit Shop", fill=(30, 80, 40), font=f_eng_head, anchor="mm")
    draw.text((280, 140), "Date: 10/10/26", fill=(40, 40, 40), font=f_date, anchor="mm")
    draw.line([(30, 165), (530, 165)], fill=(60, 100, 60), width=2)

    # Handwritten fresh produce items
    ink_color = (20, 50, 120)
    items = [
        ("Aloo 5kg", "450"),
        ("Pyaz 3kg", "390"),
        ("Tamatar 2kg", "260"),
        ("Adrak 250g", "220"),
        ("Lehsan 250g", "280"),
    ]

    y = 210
    for name, price in items:
        draw.text((45, y), name, fill=ink_color, font=f_hand)
        draw.text((515, y), price, fill=ink_color, font=f_hand, anchor="ra")
        y += 75

    draw.line([(30, y), (530, y)], fill=(80, 80, 80), width=2)
    y += 45

    draw.text((280, y), "Total: 1600 = کل", fill=ink_color, font=f_urdu, anchor="mm")
    bbox = [100, y - 35, 460, y + 35]
    draw.ellipse(bbox, outline=(20, 50, 130), width=3)

    # Dark green Pakistani marble counter background
    bg_w, bg_h = 1000, 1450
    bg = Image.new("RGBA", (bg_w, bg_h), (45, 68, 55, 255))
    # Marble vein simulation with pale white/green veins
    bg_arr = np.array(bg)
    x_idx = np.arange(bg_w)[None, :]
    y_idx = np.arange(bg_h)[:, None]
    veins = (np.sin((x_idx * 0.015) + (y_idx * 0.02) + np.sin(y_idx * 0.01) * 3) * 22).astype(np.int16)
    veins2 = (np.cos((x_idx * 0.03) - (y_idx * 0.01)) * 15).astype(np.int16)
    for c in range(3):
        bg_arr[:, :, c] = np.clip(bg_arr[:, :, c].astype(np.int16) + veins + veins2, 0, 255).astype(np.uint8)
    bg = Image.fromarray(bg_arr, "RGBA")

    # Rotate slip by 8 degrees
    rotated_slip = slip.rotate(8, resample=Image.BICUBIC, expand=True)

    shadow = Image.new("RGBA", rotated_slip.size, (0, 0, 0, 110))
    shadow.putalpha(rotated_slip.split()[3].point(lambda a: 110 if a > 0 else 0))
    shadow = shadow.filter(ImageFilter.GaussianBlur(14))

    cx = (bg_w - rotated_slip.width) // 2
    cy = (bg_h - rotated_slip.height) // 2
    bg.paste(shadow, (cx + 14, cy + 20), shadow)
    bg.paste(rotated_slip, (cx, cy), rotated_slip)

    out_path = os.path.join(OUTPUT_DIR, "challenging_greengrocer_marble.jpg")
    bg.convert("RGB").save(out_path, quality=92)
    print("Generated:", out_path)


# ── 4. POS Cash Register Roll with Vertical Crease & Barcode ──────────────────
def generate_pos_creased_roll():
    w_slip, h_slip = 520, 1180
    slip = Image.new("RGBA", (w_slip, h_slip), (250, 250, 248, 255))
    draw = ImageDraw.Draw(slip)

    f_store = get_font("consola.ttf", 26)
    f_sub = get_font("consola.ttf", 17)
    f_body = get_font("consola.ttf", 19)
    f_bold = get_font("consolab.ttf", 20)

    # Header
    draw.text((260, 40), "*** NAHEED SUPERMARKET ***", fill=(20, 20, 20), font=f_store, anchor="mm")
    draw.text((260, 75), "BRANCH: BAHADURABAD, KARACHI", fill=(50, 50, 50), font=f_sub, anchor="mm")
    draw.text((260, 100), "POS TERMINAL: 04  CASHIER: ALI", fill=(50, 50, 50), font=f_sub, anchor="mm")
    draw.text((260, 125), "DATE: 12-OCT-2026  TIME: 19:45", fill=(30, 30, 30), font=f_sub, anchor="mm")
    draw.text((260, 150), "=" * 38, fill=(60, 60, 60), font=f_sub, anchor="mm")

    # Column header
    draw.text((25, 175), "ITEM           QTY   RATE     AMOUNT", fill=(20, 20, 20), font=f_bold)
    draw.text((260, 200), "-" * 38, fill=(80, 80, 80), font=f_sub, anchor="mm")

    items = [
        ("OLPERS MILK 1.5L", "1", "420.00", "420.00"),
        ("NAT KETCHUP 800G", "1", "480.00", "480.00"),
        ("SHAN BIRYANI 50G", "2", "140.00", "280.00"),
        ("DAWN BREAD LARGE", "1", "190.00", "190.00"),
        ("TUC CRACKERS",     "1", "110.00", "110.00"),
    ]

    y = 230
    for name, qty, rate, amt in items:
        draw.text((25, y), name, fill=(25, 25, 25), font=f_body)
        draw.text((260, y), qty, fill=(25, 25, 25), font=f_body, anchor="mm")
        draw.text((385, y), rate, fill=(25, 25, 25), font=f_body, anchor="ra")
        draw.text((495, y), amt, fill=(25, 25, 25), font=f_body, anchor="ra")
        y += 50

    draw.text((260, y), "-" * 38, fill=(80, 80, 80), font=f_sub, anchor="mm")
    y += 25

    draw.text((25, y), "SUBTOTAL:", fill=(30, 30, 30), font=f_bold)
    draw.text((495, y), "1480.00", fill=(30, 30, 30), font=f_bold, anchor="ra")
    y += 35
    draw.text((25, y), "TOTAL ITEMS: 5", fill=(50, 50, 50), font=f_sub)
    y += 35
    draw.text((25, y), "TOTAL AMOUNT (PKR):", fill=(10, 10, 10), font=f_bold)
    draw.text((495, y), "1480.00", fill=(10, 10, 10), font=f_bold, anchor="ra")
    y += 40
    draw.text((260, y), "=" * 38, fill=(60, 60, 60), font=f_sub, anchor="mm")
    y += 35

    # Simulated Barcode
    bar_x = 90
    bar_y = y
    bar_w = 340
    bar_h = 70
    draw.rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], fill=(255, 255, 255))
    random.seed(42)
    bx = bar_x + 10
    while bx < bar_x + bar_w - 15:
        bw = random.choice([2, 3, 4, 6])
        draw.rectangle([bx, bar_y + 5, bx + bw, bar_y + bar_h - 15], fill=(20, 20, 20))
        bx += bw + random.choice([2, 3, 5])
    draw.text((260, bar_y + bar_h - 10), "8 964001 234567", fill=(40, 40, 40), font=f_sub, anchor="mm")

    y = bar_y + bar_h + 35
    draw.text((260, y), "THANK YOU FOR SHOPPING!", fill=(60, 60, 60), font=f_sub, anchor="mm")

    # Vertical crease down the center
    crease_x = 260
    crease_overlay = Image.new("RGBA", (w_slip, h_slip), (0, 0, 0, 0))
    c_draw = ImageDraw.Draw(crease_overlay)
    c_draw.line([(crease_x, 0), (crease_x, h_slip)], fill=(0, 0, 0, 50), width=4)
    c_draw.line([(crease_x + 3, 0), (crease_x + 3, h_slip)], fill=(255, 255, 255, 60), width=3)
    crease_overlay = crease_overlay.filter(ImageFilter.GaussianBlur(2))
    slip = Image.alpha_composite(slip, crease_overlay)

    # Dark granite kitchen counter background
    bg_w, bg_h = 850, 1550
    bg = Image.new("RGBA", (bg_w, bg_h), (38, 40, 44, 255))
    bg_arr = np.array(bg)
    speckles = np.random.choice([0, 25, 45], size=bg_arr.shape[:2], p=[0.85, 0.10, 0.05]).astype(np.int16)
    for c in range(3):
        bg_arr[:, :, c] = np.clip(bg_arr[:, :, c].astype(np.int16) + speckles, 0, 255).astype(np.uint8)
    bg = Image.fromarray(bg_arr, "RGBA")

    # Rotate slip slightly (-2.5 degrees)
    rotated_slip = slip.rotate(-2.5, resample=Image.BICUBIC, expand=True)

    shadow = Image.new("RGBA", rotated_slip.size, (0, 0, 0, 130))
    shadow.putalpha(rotated_slip.split()[3].point(lambda a: 130 if a > 0 else 0))
    shadow = shadow.filter(ImageFilter.GaussianBlur(10))

    cx = (bg_w - rotated_slip.width) // 2
    cy = (bg_h - rotated_slip.height) // 2
    bg.paste(shadow, (cx + 8, cy + 12), shadow)
    bg.paste(rotated_slip, (cx, cy), rotated_slip)

    out_path = os.path.join(OUTPUT_DIR, "challenging_pos_creased_roll.jpg")
    bg.convert("RGB").save(out_path, quality=92)
    print("Generated:", out_path)


if __name__ == "__main__":
    generate_pharmacy_receipt()
    generate_carbon_copy_karyana()
    generate_greengrocer_marble()
    generate_pos_creased_roll()
    print("All 4 challenging receipts generated successfully!")
