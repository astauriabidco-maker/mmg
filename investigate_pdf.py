import pdfplumber

def check():
    print("--- INVESTIGATION PDF CORTIZO ---")
    with pdfplumber.open("catalogs/COR VISION PLUS (Accessoires)_FR.pdf") as pdf:
        for i, page in enumerate(pdf.pages[:4]):
            if i > 0:
                print(f"--- PAGE {i} ---")
                text = page.extract_text()
                if text:
                    for line in text.split('\n'):
                        # On ne garde que les lignes intéressantes (qui ont des chiffres)
                        if any(char.isdigit() for char in line):
                            print(line)

check()
