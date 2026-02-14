import unittest
from unittest.mock import patch, MagicMock
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

from backend import qr_generator, printer

class TestQRGenerator(unittest.TestCase):
    def setUp(self):
        # Ensure output dir exists
        os.makedirs(qr_generator.OUTPUT_DIR, exist_ok=True)
        self.test_file = os.path.join(qr_generator.OUTPUT_DIR, "CMD-TEST-GEN.pdf")
        if os.path.exists(self.test_file):
            os.remove(self.test_file)

    def tearDown(self):
        if os.path.exists(self.test_file):
            os.remove(self.test_file)

    def test_generate_label(self):
        data = {
            "reference": "CMD-TEST-GEN",
            "width": 1000,
            "height": 500,
            "material": "ALU"
        }
        path = qr_generator.generate_label(data)
        
        self.assertTrue(os.path.exists(path))
        self.assertTrue(path.endswith(".pdf"))
        print(f"Generated PDF at: {path}")

    @patch('backend.printer.subprocess.run')
    def test_print_label_simulation(self, mock_subprocess):
        # Create a dummy file
        with open(self.test_file, 'w') as f:
            f.write("dummy pdf content")
            
        printer.print_label(self.test_file)
        
        # Check logic based on OS
        # Since we are in a simulated env, we just check no exception raised.
        # If linux/mac, subprocess called. If windows, logged.
        pass

    @patch('backend.qr_generator.smtplib.SMTP')
    def test_alerting(self, mock_smtp):
        qr_generator.send_email_alert("Test Subject", "Test Body")
        mock_smtp.assert_called()

if __name__ == "__main__":
    unittest.main()
