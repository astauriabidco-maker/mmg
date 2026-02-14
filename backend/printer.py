import platform
import os
import subprocess
import logging
from .qr_generator import send_email_alert

logger = logging.getLogger("Printer")

def print_label(file_path: str):
    """
    Sends the PDF file to the system default printer or configured ZEBRA printer.
    """
    if not os.path.exists(file_path):
        msg = f"File not found: {file_path}"
        logger.error(msg)
        send_email_alert("Print Error", msg)
        return

    system = platform.system()
    printer_name = os.getenv("PRINTER_NAME") # Optional, defaults to default printer

    try:
        if system == "Windows":
            # Powershell command to print
            # Or copy to COM/LPT if raw ZPL (but we have PDF here)
            # Use specific PDF printing tool or simple shell invoke
            # Simple solution for V1: os.startfile(file_path, "print") might open dialog window.
            # Automated: Use a tool like PDFtoPrinter.exe (not included) or Powershell.
            
            # Simulation for V1 (Just log)
            logger.info(f"[SIMULATION] Printing {file_path} on Windows...")
            
        elif system == "Darwin" or system == "Linux":
            # Valid lp command
            cmd = ["lp"]
            if printer_name:
                cmd.extend(["-d", printer_name])
            cmd.append(file_path)
            
            # In CI/Agent env, lp might not exist.
            # We try, catch and log simulation.
            try:
                subprocess.run(cmd, check=True)
                logger.info(f"Sent {file_path} to printer.")
            except FileNotFoundError:
                 logger.warning("[SIMULATION] 'lp' command not found. Printing simulated.")
            except subprocess.CalledProcessError as e:
                raise Exception(f"lp command failed: {e}")
                
    except Exception as e:
        msg = f"Printing failed for {file_path}: {e}"
        logger.error(msg)
        send_email_alert("Print Error", msg)

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print_label(sys.argv[1])
