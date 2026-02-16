def generate_proges_import(mmg_data: dict) -> str:
    """Génère un CSV compatible avec l'import Proges"""
    
    # Extract data from the nested JSON or the model dictionary
    ref = mmg_data.get('mmg_reference', mmg_data.get('reference', 'UNKNOWN'))
    
    # Measurements
    measurements = mmg_data.get('measurements', {})
    width = measurements.get('width_mm', mmg_data.get('width', 0))
    height = measurements.get('height_mm', mmg_data.get('height', 0))
    
    # Configuration
    config = mmg_data.get('configuration', {})
    opening_type = config.get('opening_type', mmg_data.get('opening_type', 'UNKNOWN'))
    sash_count = config.get('sash_count', mmg_data.get('sash_count', 0))
    
    material = config.get('material', mmg_data.get('material', 'ALU'))
    color = config.get('color_ral', mmg_data.get('color_ral', '7016'))
    glazing = config.get('glazing_type', mmg_data.get('glazing', '4/16/4'))
    pose = config.get('installation_type', mmg_data.get('installation_type', 'Neuf'))
    client_type = mmg_data.get('client_type', 'PARTICULIER')
    
    csv_content = f"Reference;Largeur;Hauteur;Type_ouverture;Nb_vantaux;Materiau;Couleur;Vitrage;Pose;Client_Type\n"
    csv_content += f"{ref};{width};{height};{opening_type};{sash_count};{material};{color};{glazing};{pose};{client_type}"
    
    return csv_content

def save_proges_export(mmg_data: dict, export_dir: str = "exports_proges_valides"):
    import os
    os.makedirs(export_dir, exist_ok=True)
    
    ref = mmg_data.get('mmg_reference', mmg_data.get('reference', 'UNKNOWN'))
    csv_content = generate_proges_import(mmg_data)
    
    filename = f"import_{ref}.csv"
    filepath = os.path.join(export_dir, filename)
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(csv_content)
    
    return filepath
