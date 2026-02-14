import os
import smtplib
import logging
from email.mime.text import MIMEText
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
import qrcode

# Config
LABEL_WIDTH = 50 * mm
LABEL_HEIGHT = 30 * mm
OUTPUT_DIR = os.getenv("LABEL_OUTPUT_DIR", "./output/labels")
SMTP_SERVER = os.getenv("SMTP_SERVER", "localhost")
SMTP_PORT = int(os.getenv("SMTP_PORT", 1025))
os.makedirs(OUTPUT_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("QRGenerator")

def generate_label(data: dict) -> str:
    """
    Generates a 50x30mm PDF label.
    Data must contain: reference, width, height, material.
    Output: Path to generated PDF.
    """
    try:
        ref = data.get("reference", "UNKNOWN")
        width = data.get("width", 0)
        height = data.get("height", 0)
        material = data.get("material", "UNK")
        
        # QR Content: CMD-XXXX|LxH|PVC
        qr_content = f"{ref}|{width}x{height}|{material}"
        
        filename = f"{ref}.pdf"
        file_path = os.path.join(OUTPUT_DIR, filename)
        
        # 1. Generate QR Image temp
        qr = qrcode.QRCode(box_size=10, border=0) # Border 0 for max space
        qr.add_data(qr_content)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        qr_path = os.path.join(OUTPUT_DIR, f"temp_qr_{ref}.png")
        img.save(qr_path)
        
        # 2. Create PDF
        c = canvas.Canvas(file_path, pagesize=(LABEL_WIDTH, LABEL_HEIGHT))
        
        # Draw QR (Left side, square)
        # 25mm size approx
        c.drawImage(qr_path, 2*mm, 2.5*mm, width=25*mm, height=25*mm)
        
        # Draw Text (Right side)
        c.setFont("Helvetica-Bold", 8)
        text_x = 28 * mm
        
        # Line 1: CMD-XXXX
        c.drawString(text_x, 20*mm, ref)
        
        # Line 2: LxH mm
        c.setFont("Helvetica", 7)
        c.drawString(text_x, 15*mm, f"{width}x{height} mm")
        
        # Line 3: Material
        c.setFont("Helvetica-Bold", 7)
        c.drawString(text_x, 10*mm, material)
        
        c.showPage()
        c.save()
        
        # Cleanup temp QR
        if os.path.exists(qr_path):
            os.remove(qr_path)
            
        logger.info(f"Label generated: {file_path}")
        return file_path

    except Exception as e:
        msg = f"Failed to generate label for {data}: {e}"
        logger.error(msg)
        send_email_alert("Label Generation Error", msg)
        raise e

def send_email_alert(subject, body):
    """
    Sends a simple email alert via SMTP.
    For V1/Dev, this might just log if SMTP not reached.
    """
    try:
        msg = MIMEText(body)
        msg['Subject'] = f"[ALERTE ATELIER] {subject}"
        msg['From'] = "alert@atelier.local"
        msg['To'] = "admin@atelier.local"

        # Timeout short to avoid blocking
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=2) as server:
            server.send_message(msg)
        logger.info("Alert email sent.")
    except Exception as e:
        logger.warning(f"Could not send email alert: {e} (Check SMTP config)")

if __name__ == "__main__":
    # Test
    dummy = {"reference": "CMD-TEST-01", "width": 1200, "height": 800, "material": "PVC"}
    print(generate_label(dummy))
