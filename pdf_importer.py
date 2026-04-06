import os
import re
import pdfplumber
from backend.database import SessionLocal, engine
from backend import models

models.Base.metadata.create_all(bind=engine)
CATALOGS_DIR = "catalogs"

def identify_supplier(filename, first_page_text):
    text_to_search = (filename + " " + first_page_text).upper()
    if "CORTIZO" in text_to_search or "COR " in text_to_search or "PLEGABLE" in text_to_search or "MILLENNIUM" in text_to_search:
        return "CORTIZO", re.compile(r'\b(\d{6})\b') # 6 chiffres stricts
    elif "VEKA" in text_to_search:
        return "VEKA", re.compile(r'\b(\d{3}\.\d{3})\b') # ex: 101.214
    elif "REHAU" in text_to_search:
        return "REHAU", re.compile(r'\b(\d{7})\b') # ex: 1523451
    elif "SCHUCO" in text_to_search or "SCHÜCO" in text_to_search:
        return "SCHUCO", re.compile(r'\b(\d{6})\b') 
    elif "TECHNAL" in text_to_search:
        return "TECHNAL", re.compile(r'\b([A-Z0-9]{5,8})\b')
    else:
        # Fournisseur Inconnu, tentative de regex générique (Lettres, chiffres, tirets de 5 à 12 caractères)
        return "FOURNISSEUR_INCONNU", re.compile(r'\b([A-Z0-9.\-]{5,12})\b')

def parse_pdf_catalog(filename):
    filepath = os.path.join(CATALOGS_DIR, filename)
    if filename.startswith("."): return # Ignorer fichiers cachés mac .DS_Store
    
    db = SessionLocal()
    print(f"\n--- 📖 Scanner Universel en cours : {filename} ---")
    
    items_added = 0
    supplier_name = "INCONNU"
    
    try:
        with pdfplumber.open(filepath) as pdf:
            # Identifier le fournisseur grâce à la première page
            first_page = pdf.pages[0].extract_text() or ""
            supplier_name, ref_pattern = identify_supplier(filename, first_page)
            print(f"👁️‍🗨️ IA : J'ai identifié le fournisseur [{supplier_name}] ! J'adapte ma vision spatiale.")
            
            # Pour la démo avancée, on lit un maximum de pages (limité à 30 pour la vitesse du V2)
            for page_num, page in enumerate(pdf.pages[:30]):
                text = page.extract_text()
                if not text: continue
                
                lines = text.split('\n')
                for i, line in enumerate(lines):
                    refs = ref_pattern.findall(line)
                    for ref in refs:
                        name = f"Article {supplier_name}"
                        if i > 0 and not ref_pattern.match(lines[i-1]):
                            # Tentative de capture description
                            name = lines[i-1][:45].strip()
                            
                        # V3 PIM Logic
                        base_ref = f"{supplier_name[:3]}-FAM-{ref[:3]}"
                        
                        existing_prod = db.query(models.Product).filter_by(reference_base=base_ref).first()
                        if not existing_prod:
                            existing_prod = models.Product(
                                reference_base=base_ref,
                                name=name,
                                material_type="INCONNU / A TRIER",
                                supplier=supplier_name,
                                unit="pce"
                            )
                            db.add(existing_prod)
                            db.flush()
                            
                        existing_var = db.query(models.ProductVariant).filter_by(reference=ref).first()
                        if not existing_var:
                            variant = models.ProductVariant(
                                product_id=existing_prod.id,
                                reference=ref,
                                color="STANDARD",
                                supplier_reference=ref,
                                quantity_in_stock=0,
                                min_threshold=10,
                                location="RECEPTION"
                            )
                            db.add(variant)
                            items_added += 1
                            if items_added % 50 == 0:
                                print(f"[...] {items_added} articles ingérés...")
                                
        db.commit()
    except Exception as e:
        print(f"❌ Erreur sur {filename}: {e}")
        
    db.close()
    print(f"✅ {items_added} références de [{supplier_name}] ont été intégrées avec succès !")

if __name__ == "__main__":
    if not os.path.exists(CATALOGS_DIR):
        print("Dossier introuvable.")
    else:
        pdfs = [f for f in os.listdir(CATALOGS_DIR) if f.endswith('.pdf')]
        print(f"🚀 Début de l'ingestion massive de {len(pdfs)} catalogues...")
        for pdf in pdfs:
            parse_pdf_catalog(pdf)
