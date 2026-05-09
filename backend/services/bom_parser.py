import csv
import io
import re

def parse_bom_file(content: str, filename: str) -> list[dict]:
    """
    Parse un fichier de nomenclature (BOM) issu de Orgadata / Proges / Chacal.
    Supporte CSV basique ou extraction textuelle.
    Retourne une liste: [{"reference": "PROF-ALU-01", "quantity": 5.0}, ...]
    """
    results = []
    
    # Try to parse as CSV first
    if filename.endswith(".csv"):
        # Detect delimiter
        delimiter = ';' if ';' in content.split('\n')[0] else ','
        reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
        
        # Orgadata/Proges typically export headers like "Reference", "Qte", "Quantite", "Longueur"
        ref_keys = ['Reference', 'Référence', 'Code', 'Article']
        qty_keys = ['Qte', 'Quantite', 'Quantité', 'Qté', 'Longueur', 'Length']
        
        for row in reader:
            ref = None
            qty = 0.0
            
            # Find matching keys in the row
            for key in row.keys():
                if not key: continue
                k_upper = key.strip().upper()
                
                for rk in ref_keys:
                    if rk.upper() in k_upper:
                        ref = row[key].strip()
                        break
                
                for qk in qty_keys:
                    if qk.upper() in k_upper:
                        try:
                            # Handle European comma decimals
                            val_str = row[key].strip().replace(',', '.')
                            qty = float(val_str)
                        except ValueError:
                            pass
                        break
                        
            if ref and qty > 0:
                results.append({
                    "reference": ref,
                    "quantity": qty
                })
                
        return results

    # Fallback to Regex for raw XML / Text outputs from LogiKal
    # Simplistic heuristic: looks for Reference="XYZ" Quantity="12.5"
    # or <Article Code="XYZ" Qty="12.5" />
    ref_pattern = r'(?:Reference|Code|Article)=["\']([^"\']+)["\']'
    qty_pattern = r'(?:Quantity|Qty|Quantite|Qte)=["\']([0-9.,]+)["\']'
    
    lines = content.split('\n')
    for line in lines:
        ref_match = re.search(ref_pattern, line, re.IGNORECASE)
        qty_match = re.search(qty_pattern, line, re.IGNORECASE)
        
        if ref_match and qty_match:
            try:
                qty_val = float(qty_match.group(1).replace(',', '.'))
                results.append({
                    "reference": ref_match.group(1).strip(),
                    "quantity": qty_val
                })
            except ValueError:
                pass

    return results
