import re
import json

text = """
DEVIS N°MMG25020111 - ARS
Nom du client : ARS
Mr AKDEREN
... (full text provided by user)
""" # Simplified for the script, I will use the actual string in my logic

def test_extraction(full_text):
    # 1. Global fields
    client_match = re.search(r"Nom du client\s*:\s*(.*)", full_text, re.IGNORECASE)
    client = client_match.group(1).strip() if client_match else "UNKNOWN"
    
    ref_match = re.search(r"DEVIS N°(\w+)", full_text)
    base_ref = ref_match.group(1) if ref_match else "UNKNOWN"

    # 2. Find Sections (Position ... Pce)
    # Looking for: "BAT D 1 Pce", "BAT B - RdC Droit 1 Pce"
    pos_matches = list(re.finditer(r"^([A-Z][^:]+?)\s+(\d+)\s+Pce", full_text, re.MULTILINE))
    
    results = []
    for i in range(len(pos_matches)):
        start = pos_matches[i].start()
        end = pos_matches[i+1].start() if i+1 < len(pos_matches) else len(full_text)
        section_text = full_text[start:end]
        
        pos_name = pos_matches[i].group(1).strip()
        qty = int(pos_matches[i].group(2))
        
        # Dimensions in this section
        dim_match = re.search(r"châssis\s+(\d+)\s+mm\s+x\s+(\d+)\s+mm", section_text)
        w = dim_match.group(1) if dim_match else 0
        h = dim_match.group(2) if dim_match else 0
        
        # Color in this section
        color_match = re.search(r"RAL\s+(\d+\w*)\s*\(([^)]+)\)", section_text)
        color = f"RAL {color_match.group(1)} ({color_match.group(2)})" if color_match else "UNKNOWN"
        
        results.append({
            "reference": f"CMD-{base_ref}-{pos_name.replace(' ', '-')}",
            "client": client,
            "quantity": qty,
            "width": float(w),
            "height": float(h),
            "color": color,
            "material": "ALU" if "Aluminium" in full_text or "Cortizo" in section_text else "PVC"
        })
    
    return results

# I'll test it in my head first or use a small run if possible.
