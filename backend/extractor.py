import logging
import re
import os
import json
from pypdf import PdfReader
from typing import List, Dict

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("extractor.log")
    ]
)
logger = logging.getLogger("PDFExtractor")

class PDFExtractor:
    def __init__(self):
        # Global Patterns
        self.devis_ref_pattern = re.compile(r"DEVIS N°\s*(\d+(?:-\d+)?)", re.IGNORECASE)
        self.client_pattern = re.compile(r"Nom du client\s*:\s*(.*)", re.IGNORECASE)
        
        # Position Splitter
        self.pos_pattern = re.compile(r"POS\s*(\d+)[:\s]+(\d+)\s*(?:Pce|PCE)", re.MULTILINE | re.IGNORECASE)
        
        # Detail Patterns (per position)
        self.dim_pattern = re.compile(r"(?:châssis\s+|L:\s*)(\d+)\s*(?:mm\s+x\s+|H:\s*)(\d+)\s*(?:mm)?", re.IGNORECASE)
        self.color_pattern = re.compile(r"(?:RAL\s+|Couleur:\s*)(\d+\w*)\s*(?:\(([^)]+)\))?", re.IGNORECASE)
        self.system_pattern = re.compile(r"(?:Système|Gamme):\s*(.*)", re.IGNORECASE)

    def process(self, file_path: str) -> List[Dict]:
        """
        Main entry point. Returns a list of extracted positions.
        """
        logger.info(f"Processing file: {file_path}")
        
        try:
            ext = os.path.splitext(file_path)[1].lower()
            filename = os.path.basename(file_path)
            
            # Default reference from filename
            file_ref = "UNKNOWN"
            file_ref_match = re.search(r"((?:MMG|CMD|REF)?\d+[\w-]*)", filename, re.IGNORECASE)
            if file_ref_match:
                file_ref = file_ref_match.group(1)

            text = ""
            if ext == '.txt':
                with open(file_path, 'r', encoding='utf-8') as f:
                    text = f.read()
            else:
                try:
                    reader = PdfReader(file_path)
                    for page in reader.pages:
                        text += page.extract_text() + "\n"
                except Exception as e:
                    logger.error(f"Error reading PDF: {e}")
            
            # 1. Global Field Extraction
            global_ref_match = self.devis_ref_pattern.search(text)
            devis_ref = global_ref_match.group(1) if global_ref_match else file_ref
            
            client_match = self.client_pattern.search(text)
            client = client_match.group(1).strip() if client_match else "UNKNOWN"
            
            material = "ALU" if ("Aluminium" in text or "Cortizo" in text) else "PVC"

            # 2. Multi-Position Extraction
            positions = list(self.pos_pattern.finditer(text))
            
            if not positions:
                # Fallback to single item if no positions found
                logger.warning("No explicit positions found, performing single item extraction.")
                return [self._create_result(text, devis_ref, client, material, "MAIN")]

            results = []
            for i, match in enumerate(positions):
                start = match.start()
                end = positions[i+1].start() if i+1 < len(positions) else len(text)
                section_text = text[start:end]
                
                pos_name = f"POS-{match.group(1)}"
                qty = int(match.group(2))
                
                res = self._create_result(section_text, devis_ref, client, material, pos_name)
                res["quantity"] = qty
                results.append(res)
            
            # Send all to API
            for r in results:
                self.send_to_api(r)
                
            return results

        except Exception as e:
            logger.error(f"Critical error in extractor: {e}", exc_info=True)
            return [{"error": str(e)}]

    def _create_result(self, text: str, base_ref: str, client: str, material: str, pos_name: str) -> Dict:
        # Dimensions
        w, h = 0.0, 0.0
        dim_match = self.dim_pattern.search(text)
        if dim_match:
            w = float(dim_match.group(1))
            h = float(dim_match.group(2))
        
        # Color
        color = "UNKNOWN"
        color_match = self.color_pattern.search(text)
        if color_match:
            color = f"RAL {color_match.group(1)} ({color_match.group(2)})"
            
        # System
        sys_type = "UNKNOWN"
        sys_match = self.system_pattern.search(text)
        if sys_match:
            sys_type = sys_match.group(1).strip()

        # Clean reference
        clean_pos = pos_name.replace(" ", "-").replace("/", "-")
        full_ref = f"CMD-{base_ref}-{clean_pos}"
        if len(full_ref) > 50: # Pruning long refs
             full_ref = full_ref[:50]

        return {
            "reference": full_ref,
            "width": w,
            "height": h,
            "material": material,
            "client_name": client,
            "color": color,
            "system_type": sys_type,
            "quantity": 1
        }

    def send_to_api(self, data: dict):
        import requests
        API_URL = "http://127.0.0.1:8000/v2/ingest/order"
        try:
            response = requests.post(API_URL, json=data)
            if response.status_code in [200, 201]:
                logger.info(f"SUCCESS: Sent {data['reference']} to API.")
            else:
                logger.error(f"FAILURE: API Error ({response.status_code}) for {data['reference']}: {response.text}")
        except Exception as e:
            logger.error(f"CONNECTION ERROR: Failed to reach API at {API_URL}: {e}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        e = PDFExtractor()
        print(json.dumps(e.process(sys.argv[1]), indent=2))
