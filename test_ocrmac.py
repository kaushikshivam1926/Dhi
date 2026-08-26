import fitz
import os
import tempfile
from ocrmac import ocrmac

def test_ocr(pdf_path):
    doc = fitz.open(pdf_path)
    page = doc[0]
    pix = page.get_pixmap()
    with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
        pix.save(tmp.name)
        print(f"Performing OCR on {pdf_path} page 0...")
        annotations = ocrmac.OCR(tmp.name).recognize()
        # annotations is a list of (text, confidence, bounding_box)
        text = "\n".join([a[0] for a in annotations])
        print("Extracted Text Preview:")
        print(text[:500])

if __name__ == "__main__":
    test_ocr("RawMaterials/FT US ³¹'⁰³'²⁰²⁶.pdf")
