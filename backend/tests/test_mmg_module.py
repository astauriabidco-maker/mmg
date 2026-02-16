import requests
import base64
import json

BASE_URL = "http://localhost:8000/v2/mmg"

# Sample 1x1 transparent PNG pixel in base64
SAMPLE_B64 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="

def test_mmg_lifecycle():
    print("--- Testing MMG Lifecycle ---")
    
    # 1. Create
    payload = {
        "client": {
            "name": "Jean Dupont",
            "contact": "0601020304",
            "address": "123 Rue de la Paix, Paris",
            "site_address": "456 Avenue des Champs",
            "email": "jean.dupont@email.com"
        },
        "measurements": {
            "width_mm": 1200,
            "height_mm": 1450,
            "passage_height_mm": 1400
        },
        "options": {
            "sill_height_mm": 50,
            "transom_height_mm": 0,
            "shutter_type": "gauche"
        },
        "configuration": {
            "view": "interior",
            "opening_type": "tirant",
            "opening_side": "droite",
            "sash_count": 2,
            "material": "ALU",
            "product_series": "Premium",
            "color_ral": "7016"
        },
        "logistics": {
            "floor_number": 1,
            "access_difficulty": "Standard",
            "environment": "Standard"
        },
        "photos": [SAMPLE_B64],
        "signature": SAMPLE_B64
    }
    
    try:
        print("Creating dossier...")
        resp = requests.post(BASE_URL + "/", json=payload)
        resp.raise_for_status()
        data = resp.json()
        dossier_id = data["id"]
        ref = data["reference"]
        print(f"SUCCESS: Created dossier {ref} (ID: {dossier_id})")
        
        # 2. List
        print("Listing dossiers...")
        resp = requests.get(BASE_URL + "/")
        resp.raise_for_status()
        l = resp.json()
        print(f"SUCCESS: Found {len(l)} dossiers")
        
        # 3. Detail
        print(f"Getting detail for ID {dossier_id}...")
        resp = requests.get(f"{BASE_URL}/{dossier_id}")
        resp.raise_for_status()
        detail = resp.json()
        print(f"SUCCESS: Detail fetched. Photos found: {len(detail['photos'])}")
        print(f"Signature path: {detail['signature']}")
        
        # 4. Update Status (Trigger Proges)
        print("Validating dossier (Triggers Proges Export)...")
        resp = requests.patch(f"{BASE_URL}/{dossier_id}/status", json={"status": "VALIDATED"})
        resp.raise_for_status()
        print("SUCCESS: Status updated to VALIDATED")
        
        # 5. Send Quote
        print("Sending quote...")
        resp = requests.post(f"{BASE_URL}/{dossier_id}/send-quote")
        resp.raise_for_status()
        print(f"SUCCESS: Quote sent. Message: {resp.json()['message']}")

    except Exception as e:
        print(f"FAILURE: {e}")
        if hasattr(e, 'response') and e.response:
            print(f"Response: {e.response.text}")

if __name__ == "__main__":
    test_mmg_lifecycle()
