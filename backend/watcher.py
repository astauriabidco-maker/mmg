
import time
import os
import shutil
import logging
from .extractor import PDFExtractor

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("Watcher")

INPUT_DIR = "input_orders"
PROCESSED_DIR = "processed_orders"
ERROR_DIR = "error_orders"

class Watcher:
    def __init__(self):
        # Ensure directories exist
        for d in [INPUT_DIR, PROCESSED_DIR, ERROR_DIR]:
            if not os.path.exists(d):
                os.makedirs(d)
                logger.info(f"Created directory: {d}")
                
        self.extractor = PDFExtractor()
        self.is_running = True

    def run(self):
        logger.info(f"Watcher started. Monitoring {INPUT_DIR}...")
        while self.is_running:
            try:
                self.check_folder()
            except Exception as e:
                logger.error(f"Error in watcher loop: {e}")
            
            time.sleep(5) # Check every 5 seconds

    def check_folder(self):
        # Re-check existence just in case
        if not os.path.exists(INPUT_DIR):
            return

        files = [f for f in os.listdir(INPUT_DIR) if f.lower().endswith(('.pdf', '.txt'))]
        
        for filename in files:
            file_path = os.path.join(INPUT_DIR, filename)
            logger.info(f"New file detected: {filename}")
            
            try:
                # Process returns a List[Dict]
                results = self.extractor.process(file_path)
                
                # Check if any result indicated a critical error
                failed = any("error" in r for r in results)
                
                target_dir = PROCESSED_DIR
                if failed:
                    target_dir = ERROR_DIR
                    for r in results:
                        if "error" in r:
                            logger.error(f"Error in {filename}: {r['error']}")
                
                shutil.move(file_path, os.path.join(target_dir, filename))
                logger.info(f"Moved {filename} to {target_dir}")
                
            except Exception as e:
                logger.error(f"CRITICAL: Failed to move/process {filename}: {e}")

if __name__ == "__main__":
    watcher = Watcher()
    watcher.run()
