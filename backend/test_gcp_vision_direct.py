"""
Direct Google Cloud Vision API Test (Zero Local OCR Processing)
Sends raw receipt bytes directly to GCP Cloud Vision servers.
"""

import os
import sys
import time
from pathlib import Path

# Explicitly set the credentials path
cred_path = Path(__file__).resolve().parent / "credentials" / "google_vision_key.json"
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(cred_path)

try:
    from google.cloud import vision
except ImportError as e:
    print(f"Error: google-cloud-vision not installed: {e}")
    sys.exit(1)

def run_direct_vision_ocr(image_path: str):
    print("=" * 65)
    print("  ReceiptLedger – Direct Google Cloud Vision API Test")
    print("=" * 65)
    print(f"[*] Target Image       : {image_path}")
    print(f"[*] Credentials File   : {cred_path}")
    print(f"[*] Local Preprocessing: NONE (100% cloud processed)")
    print(f"[*] Local OCR Fallbacks: DISABLED (pure GCP API call)")
    print("-" * 65)

    if not Path(image_path).exists():
        print(f"[!] Error: Image not found at {image_path}")
        return

    # 1. Read raw image bytes
    with open(image_path, "rb") as f:
        image_bytes = f.read()
    print(f"[+] Loaded raw image: {len(image_bytes):,} bytes ({len(image_bytes)/1024:.1f} KB)")

    # 2. Initialize official GCP Client
    print("[*] Contacting Google Cloud Vision endpoint (vision.googleapis.com)...")
    start_time = time.time()
    
    client = vision.ImageAnnotatorClient()
    image = vision.Image(content=image_bytes)

    # 3. Call TEXT_DETECTION API
    response = client.text_detection(image=image)
    elapsed = time.time() - start_time

    if response.error.message:
        print(f"[!] GCP API Error: {response.error.message}")
        return

    # 4. Parse Results
    annotations = response.text_annotations
    if not annotations:
        print("[!] No text detected by Cloud Vision.")
        return

    full_text = annotations[0].description
    individual_words = annotations[1:]

    print(f"[+] SUCCESS! API responded in {elapsed:.2f} seconds.")
    print(f"[+] Total detected tokens/words: {len(individual_words)}")
    print("=" * 65)
    print("  RAW FULL TEXT EXTRACTED BY GOOGLE CLOUD VISION:")
    print("=" * 65)
    print(full_text.strip())
    print("=" * 65)

    # Display some bounding box highlights
    print("\n--- Sample Word Tokens & Coordinates from GCP ---")
    for idx, token in enumerate(individual_words[:8], 1):
        vertices = [(v.x, v.y) for v in token.bounding_poly.vertices]
        print(f"  [{idx:02d}] '{token.description}' -> BoundingBox: {vertices}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        img = sys.argv[1]
    else:
        sample_path = Path(__file__).resolve().parents[1] / "data" / "sample_receipts" / "javed_nahari_sample.png"
        img = str(sample_path if sample_path.exists() else Path(__file__).resolve().parent / "test_receipt.png")
    run_direct_vision_ocr(img)
