import fitz
import sys

def check_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    print(f"Total pages: {len(doc)}")
    for i in range(min(3, len(doc))):
        page = doc[i]
        text = page.get_text()
        images = page.get_images()
        print(f"Page {i}: Length of text: {len(text)}. Number of images: {len(images)}")

if __name__ == "__main__":
    check_pdf(sys.argv[1])
