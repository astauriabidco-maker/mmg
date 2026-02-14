import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Mock modules if they don't exist to allow import of the script
class MockModule(MagicMock):
    pass

sys.modules.setdefault('watchdog', MockModule())
sys.modules.setdefault('watchdog.observers', MockModule())
sys.modules.setdefault('watchdog.events', MockModule())
sys.modules.setdefault('pypdf', MockModule())
sys.modules.setdefault('qrcode', MockModule())
sys.modules.setdefault('requests', MockModule())

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

# Now import the module to test
from backend import surveillance

class TestSurveillance(unittest.TestCase):
    
    def test_extract_logic_pvc(self):
        # We need to test the logic inside extract_order_data
        # But since we mocked pypdf, we need to inspect how the function uses it
        
        # In the script, it does:
        # reader = PdfReader(pdf_path)
        # for page in reader.pages: text += page.extract_text()
        
        # We can just check regex logic by extracting the logic to a separate function 
        # or mocking PdfReader inside the function call.
        
        with patch('backend.surveillance.PdfReader') as MockPdfReader:
             # Setup Mock
            mock_reader = MockPdfReader.return_value
            mock_page = MagicMock()
            mock_page.extract_text.return_value = "Commande Client\nRef: CMD-8888\nLargeur: 1500\nHauteur: 2150\nMatière: PVC Blanc"
            mock_reader.pages = [mock_page]
            
            # Run
            data = surveillance.extract_order_data("dummy.pdf")
            
            # Assert
            self.assertEqual(data["reference"], "CMD-8888")
            self.assertEqual(data["width"], 1500.0)
            self.assertEqual(data["height"], 2150.0)
            self.assertEqual(data["material"], "PVC")

    def test_extract_logic_alu(self):
         with patch('backend.surveillance.PdfReader') as MockPdfReader:
            # Setup Mock
            mock_reader = MockPdfReader.return_value
            mock_page = MagicMock()
            mock_page.extract_text.return_value = "Fabrication ALU\nLargeur: 800\nHauteur: 600\nRef: CMD-9999\nType: ALU"
            mock_reader.pages = [mock_page]
            
            # Run
            data = surveillance.extract_order_data("dummy_alu.pdf")
            
            # Assert
            self.assertEqual(data["reference"], "CMD-9999")
            self.assertEqual(data["width"], 800.0) # regex expects 'Largeur:...', might fail if my test string above is too loose.
            # Wait, my regex in surveillance.py is:
            # width_match = re.search(r"Largeur\s*[:=]?\s*(\d+)", text, re.IGNORECASE)
            # My test string must match that.
            
            # Re-setup mock with matching text
            mock_page.extract_text.return_value = "Ref: CMD-9999\nLargeur: 800\nHauteur: 600\nMatière: ALU"
            
            data = surveillance.extract_order_data("dummy_alu.pdf")
            
            self.assertEqual(data["reference"], "CMD-9999")
            self.assertEqual(data["width"], 800.0)
            self.assertEqual(data["material"], "ALU")

if __name__ == '__main__':
    unittest.main()
