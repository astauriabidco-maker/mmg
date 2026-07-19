import time
import os
import re
import sys
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from pypdf import PdfReader
import qrcode
import requests

# CONFIGURATION
# Local simulation of the Windows path
WATCH_DIR = os.getenv("WATCH_DIR", "./exports_proges_valides")
OUTPUT_QR_DIR = os.getenv("OUTPUT_QR_DIR", "./output/qr")
API_URL = os.getenv("API_URL", "http://localhost:8000")

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# Ensure directories exist
os.makedirs(WATCH_DIR, exist_ok=True)
os.makedirs(OUTPUT_QR_DIR, exist_ok=True)

class OrderHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        filename = event.src_path
        if filename.lower().endswith(".pdf"):
            logger.info(f"New PDF detected: {filename}")
            try:
                process_pdf(filename)
            except Exception as e:
                logger.error(f"Error processing {filename}: {e}")

def extract_order_data(pdf_path):
    """
    Extracts order data from PROGES PDF export.
    Patterns to find:
    - Reference: CMD-XXXX (Auto-generated or found in text)
      *Real world: PROGES exports often have Ref in filename or specific location.*
      *Hypothesis for V1: Regex for 'CMD-' or similar.*
    - Dimensions: 'Largeur: 1200', 'Hauteur: 2000' (Example)
    - Material: 'PVC' or 'ALU'
    """
    reader = PdfReader(pdf_path)
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"
    
    # Regex Patterns (Simplistic for V1)
    # Ref: Look for explicit "Ref: ..." or just "CMD-\d+"
    # Let's assume the filename might contain the ref, or inside text.
    # We'll search in text for simplicity and strict rules.
    
    ref_match = re.search(r"CMD-\d+", text)
    width_match = re.search(r"Largeur\s*[:=]?\s*(\d+)", text, re.IGNORECASE)
    height_match = re.search(r"Hauteur\s*[:=]?\s*(\d+)", text, re.IGNORECASE)
    
    # Material: Naive search
    material = "PVC" # Default? No, must detect.
    if "ALU" in text.upper():
        material = "ALU"
    elif "PVC" in text.upper():
        material = "PVC"
    else:
        # Fallback or strict error?
        # V1: Default to PVC if unsure or raise error. 
        # Let's be safe: If neither found, maybe it's not a valid order.
        # But for MVP, let's default to PVC or extract from filename if possible.
        pass

    if not ref_match:
        # Fallback: Try filename
        base_name = os.path.basename(pdf_path)
        ref_match = re.search(r"CMD-\d+", base_name)
    
    if not ref_match:
        raise ValueError("Reference CMD-XXXX not found in PDF or filename")
    
    reference = ref_match.group(0)
    width = float(width_match.group(1)) if width_match else 0.0
    height = float(height_match.group(1)) if height_match else 0.0
    
    return {
        "reference": reference,
        "width": width,
        "height": height,
        "material": material
    }

def generate_qr(order_data):
    """
    Generates a QR code 50x30mm (approx).
    Content: CMD-XXXX|LxH|PVC
    """
    ref = order_data["reference"]
    w = int(order_data["width"])
    h = int(order_data["height"])
    mat = order_data["material"]
    
    content = f"{ref}|{w}x{h}|{mat}"
    
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(content)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    
    # Filename
    output_path = os.path.join(OUTPUT_QR_DIR, f"{ref}.png")
    img.save(output_path)
    logger.info(f"QR Saved: {output_path}")
    return output_path

def _get_auth_headers():
    """
    Authenticate against the API using service credentials from env vars.
    """
    username = os.getenv("SURVEILLANCE_USERNAME")
    password = os.getenv("SURVEILLANCE_PASSWORD")
    if not username or not password:
        logger.warning("SURVEILLANCE_USERNAME/SURVEILLANCE_PASSWORD non définis : l'appel API sera refusé (401).")
        return {}
    try:
        response = requests.post(f"{API_URL}/token", data={"username": username, "password": password}, timeout=10)
        if response.status_code == 200:
            return {"Authorization": f"Bearer {response.json()['access_token']}"}
        logger.error(f"API auth failed: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"API auth error: {e}")
    return {}

def send_to_api(order_data):
    """
    Post data to local API to create order in DB.
    """
    try:
        payload = {
            "reference": order_data["reference"],
            "width": order_data["width"],
            "height": order_data["height"],
            "material": order_data["material"]
        }
        response = requests.post(f"{API_URL}/orders/", json=payload, headers=_get_auth_headers())
        if response.status_code in [200, 201]:
            logger.info(f"Order {order_data['reference']} synced to API.")
        elif response.status_code == 400 and "already exists" in response.text:
             logger.info(f"Order {order_data['reference']} already exists.")
        else:
            logger.error(f"API Error: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"Failed to connect to API: {e}")

def process_pdf(pdf_path):
    logger.info(f"Processing {pdf_path}...")
    try:
        data = extract_order_data(pdf_path)
        logger.info(f"Extracted: {data}")
        
        generate_qr(data)
        send_to_api(data)
        
        # Optional: Move processed file to 'Processed' folder?
        # Not explicitly requested in V1 perimeter, but good practice.
        # Staying strict to V1: Just leave it or maybe rename.
        pass
    except Exception as e:
        logger.error(f"Process Failed: {e}")

if __name__ == "__main__":
    logger.info(f"Starting Surveillance on {WATCH_DIR}")
    event_handler = OrderHandler()
    observer = Observer()
    observer.schedule(event_handler, WATCH_DIR, recursive=False)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
