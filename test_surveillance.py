import unittest
from unittest.mock import patch, MagicMock
import os
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

from backend import surveillance

class TestSurveillance(unittest.TestCase):
    
    @patch('backend.surveillance.PdfReader')
    def test_extract_order_data_pvc(self, MockPdfReader):
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

    @patch('backend.surveillance.PdfReader')
    def test_extract_order_data_alu(self, MockPdfReader):
        # Setup Mock
        mock_reader = MockPdfReader.return_value
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Fabrication ALU\nDimension: 800x600\nLargeur=800\nHauteur=600\nRef: CMD-9999\nType: ALU RAL 7016"
        mock_reader.pages = [mock_page]
        
        # Run
        data = surveillance.extract_order_data("dummy_alu.pdf")
        
        # Assert
        self.assertEqual(data["reference"], "CMD-9999")
        self.assertEqual(data["width"], 800.0)
        self.assertEqual(data["height"], 600.0)
        self.assertEqual(data["material"], "ALU")

    @patch('backend.surveillance.requests.post')
    @patch('backend.surveillance.qrcode.QRCode')
    @patch('backend.surveillance.extract_order_data')
    def test_process_pdf_flow(self, mock_extract, mock_qr_cls, mock_post):
        # Setup
        mock_extract.return_value = {
            "reference": "CMD-TEST",
            "width": 1000,
            "height": 1000,
            "material": "PVC"
        }
        mock_image = MagicMock()
        mock_qr_instance = mock_qr_cls.return_value
        mock_qr_instance.make_image.return_value = mock_image
        
        mock_post.return_value.status_code = 200
        
        # Run
        surveillance.process_pdf("test.pdf")
        
        # Verify
        mock_extract.assert_called_with("test.pdf")
        mock_qr_instance.add_data.assert_called_with("CMD-TEST|1000x1000|PVC")
        mock_image.save.assert_called()
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(kwargs['json']['reference'], "CMD-TEST")

if __name__ == '__main__':
    unittest.main()
