import os

try:
    import pdfplumber
except Exception:
    pdfplumber = None

try:
    import pytesseract
    from PIL import Image
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
except Exception:
    pytesseract = None
    Image = None


def extract_text_from_pdf(file_path):
    if pdfplumber is None:
        raise Exception("pdfplumber is not installed")
    text = ""
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            text += page_text + "\n"
    return text


def extract_text_from_image(file_path):
    if pytesseract is None or Image is None:
        raise Exception("pytesseract/Pillow not installed")
    image = Image.open(file_path)
    text = pytesseract.image_to_string(image)
    return text


def extract_text(file_path):
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        return extract_text_from_pdf(file_path)

    elif ext in [".png", ".jpg", ".jpeg"]:
        return extract_text_from_image(file_path)

    else:
        raise Exception("Unsupported file type")

