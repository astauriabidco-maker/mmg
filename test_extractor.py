import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import json

# Fix import path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

# Mock dependencies before import to avoid runtime errors on CI without Tesseract
class MockImage:
    pass

sys.modules.setdefault('pdf2image', MagicMock())
sys.modules.setdefault('pytesseract', MagicMock())

from backend.extractor import PDFExtractor

class TestPDFExtractor(unittest.TestCase):

    def setUp(self):
        self.extractor = PDFExtractor()

    @patch('backend.extractor.PdfReader')
    def test_native_extraction_ok(self, MockPdfReader):
        # Scenario: Clean digital PDF
        mock_reader = MockPdfReader.return_value
        mock_page = MagicMock()
        mock_page.extract_text.return_value = """
        PROGES EXPORT
        Ref: CMD-1001
        Largeur: 1200.5
        Hauteur: 2000
        Matière: PVC
        """
        mock_reader.pages = [mock_page]

        result = self.extractor.process("test_native.pdf")
        
        self.assertEqual(result['reference'], "CMD-1001")
        self.assertEqual(result['width_mm'], 1200.5)
        self.assertEqual(result['height_mm'], 2000.0)
        self.assertEqual(result['material'], "PVC")

    @patch('backend.extractor.convert_from_path')
    @patch('backend.extractor.pytesseract.image_to_string')
    @patch('backend.extractor.PdfReader')
    def test_ocr_fallback(self, MockPdfReader, MockOCR, MockConvert):
        # Scenario: Empty native text -> Fallback OCR
        mock_reader = MockPdfReader.return_value
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "" # Empty text (Scanned PDF)
        mock_reader.pages = [mock_page]

        # OCR Returns text
        MockConvert.return_value = ["dummy_image"]
        MockOCR.return_value = """
        SCANNED DOCUMENT
        CMD-2002
        L=800mm H=600mm
        ALU MATT
        """

        result = self.extractor.process("test_scan.pdf")
        
        # Verify Fallback triggered
        MockConvert.assert_called()
        self.assertEqual(result['reference'], "CMD-2002")
        self.assertEqual(result['width_mm'], 800.0)
        self.assertEqual(result['height_mm'], 600.0)
        self.assertEqual(result['material'], "ALU")

    @patch('backend.extractor.PdfReader')
    def test_partial_data_failure(self, MockPdfReader):
        # Scenario: Missing Height
        mock_reader = MockPdfReader.return_value
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Ref: CMD-3003 Largeur: 1000 PVC"
        mock_reader.pages = [mock_page]

        # Ensure OCR fallback is tried even if partial data
        with patch('backend.extractor.convert_from_path') as MockConvert:
            MockConvert.return_value = [] # OCR fails too
            result = self.extractor.process("test_partial.pdf")
            
            # Should have partial data or fail?
            # Current logic returns whatever it found after trying both.
            # Here it found CMD, Width, Material. Height is 0.
            self.assertEqual(result['reference'], "CMD-3003")
            self.assertEqual(result['height_mm'], 0.0)

    def test_mass_simulations(self):
        # Simulate 30 variations
        patterns = [
            ("Ref: CMD-{i} Largeur: 1000 Hauteur: 2000 PVC", "PVC", 1000, 2000),
            ("CMD-{i} L={i}0 H={i}0 ALU", "ALU", float(f"{i}0"), float(f"{i}0")),
            ("Width: 500 Height: 500 Mat: PVC Ref: CMD-{i}", "PVC", 500, 500),
        ]
        
        for i in range(1, 31):
            pattern, mat, w, h = patterns[i % 3] # Rotate patterns
            text = pattern.format(i=i)
            # Check parsing logic directly to avoid mocking overhead for 30 calls
            data = self.extractor._parse_data(text)
            
            expected_ref = str(i)
            if i % 3 == 0: expected_ref = f"{i}" # Logic matches CMD-{i}
            
            self.assertEqual(data.get('cmd'), str(i))
            self.assertEqual(float(data.get('width')), float(w))
            self.assertEqual(float(data.get('height')), float(h))
            self.assertEqual(data.get('material').upper(), mat)

if __name__ == '__main__':
    unittest.main()
