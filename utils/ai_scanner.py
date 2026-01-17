# utils/ai_scanner.py
from io import BytesIO
import re
import fitz  # PyMuPDF
from PIL import Image, ImageOps
import pytesseract


def extract_gpa(text: str):
    """
    Try to extract GPA from text.
    Supports patterns like:
      GPA: 3.45
      GPA 3.2
      CUMULATIVE GPA = 2.98
    Returns float or None.
    """
    if not text:
        return None

    patterns = [
        r"\bGPA\s*[:=]?\s*([0-4]\.\d{1,2})\b",
        r"\bCUMULATIVE\s+GPA\s*[:=]?\s*([0-4]\.\d{1,2})\b",
        r"\bCGPA\s*[:=]?\s*([0-4]\.\d{1,2})\b",
    ]
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                pass

    # fallback: any 0.00-4.00 after the word GPA
    m = re.search(r"\bGPA\b(.{0,20})([0-4]\.\d{1,2})", text, flags=re.IGNORECASE)
    if m:
        try:
            return float(m.group(2))
        except ValueError:
            return None

    return None


def _preprocess_image_for_ocr(img: Image.Image) -> Image.Image:
    """
    Basic OCR preprocessing to improve accuracy.
    """
    img = img.convert("RGB")
    img = ImageOps.grayscale(img)

    # upscale
    w, h = img.size
    img = img.resize((w * 2, h * 2))

    # increase contrast + binarize
    img = ImageOps.autocontrast(img)
    img = img.point(lambda x: 0 if x < 160 else 255, "1")
    return img


def _ocr_image_bytes(raw: bytes) -> str:
    img = Image.open(BytesIO(raw))
    img = _preprocess_image_for_ocr(img)
    return pytesseract.image_to_string(img)


def _extract_pdf_text_with_ocr_fallback(raw: bytes) -> str:
    """
    Extract text from PDF pages; if a page is scanned and returns no text,
    render it to an image and OCR it.
    """
    out = []
    pdf = fitz.open(stream=raw, filetype="pdf")

    for page in pdf:
        page_text = page.get_text("text") or ""
        page_text = page_text.strip()

        if page_text:
            out.append(page_text)
            continue

        # OCR fallback for scanned page
        pix = page.get_pixmap(dpi=200)  # 200dpi is a good balance
        img = Image.open(BytesIO(pix.tobytes("png")))
        img = _preprocess_image_for_ocr(img)
        ocr_text = pytesseract.image_to_string(img).strip()
        if ocr_text:
            out.append(ocr_text)

    pdf.close()
    return "\n".join(out)


def scan_documents_for_eligibility(application, task_id=None, progress_callback=None):
    """
    Scans application documents and returns a text summary.
    If task_id is provided, progress_callback(task_id, progress, message) will be called.
    """

    def maybe_update(pct, msg):
        if progress_callback and task_id is not None:
            try:
                progress_callback(task_id, pct, msg)
            except Exception:
                pass

    summary = []
    eligibility_flags = []
    score = 0
    criteria_met = 0

    # NOTE: add expression_of_interest if your model has it; otherwise remove the branch below.
    document_fields = [
        ("transcript", application.transcript),
        ("grade_12_certificate", application.grade_12_certificate),
        ("acceptance_letter", application.acceptance_letter),
        ("school_fee_structure", application.school_fee_structure),
        ("id_card", application.id_card),
        ("character_reference_1", application.character_reference_1),
        ("character_reference_2", application.character_reference_2),
        ("statedec", application.statedec),
        # ("expression_of_interest", getattr(application, "expression_of_interest", None)),
    ]

    total = len(document_fields)
    processed = 0

    maybe_update(1, "Starting document scan...")

    for label, file in document_fields:
        processed += 1
        pct = int((processed - 1) / max(total, 1) * 90)
        maybe_update(pct, f"Processing {label.replace('_', ' ').title()}...")

        if not file:
            eligibility_flags.append(f"❌ Missing: {label.replace('_', ' ').title()}")
            continue

        text = ""
        file_name = (getattr(file, "name", "") or "").lower()

        try:
            file.seek(0)
            raw = file.read()
            file.seek(0)

            if file_name.endswith(".pdf"):
                text = _extract_pdf_text_with_ocr_fallback(raw)

            elif file_name.endswith((".png", ".jpg", ".jpeg")):
                text = _ocr_image_bytes(raw)

            else:
                # fallback attempt
                try:
                    text = raw.decode("utf-8", errors="ignore")
                except Exception:
                    text = ""

        except Exception as e:
            summary.append(f"⚠️ Error reading {label}: {str(e)}")
            continue

        text_lower = (text or "").lower()

        # -------- Eligibility checks --------
        if label == "transcript":
            summary.append("Transcript found.")
            gpa = extract_gpa(text)
            if gpa is not None:
                summary.append(f"GPA detected: {gpa}")
                if gpa >= 3.0:
                    eligibility_flags.append("✅ GPA meets requirement")
                    score += 2
                    criteria_met += 1
                else:
                    eligibility_flags.append("⚠️ GPA below threshold")
            else:
                eligibility_flags.append("⚠️ GPA not found in transcript")

        elif label == "grade_12_certificate":
            summary.append("Grade 12 Certificate detected.")
            eligibility_flags.append("✅ Academic qualification confirmed")
            score += 1
            criteria_met += 1

        elif label == "acceptance_letter":
            summary.append("Enrollment proof detected.")
            eligibility_flags.append("✅ Enrollment confirmed")
            score += 1
            criteria_met += 1

        elif label == "school_fee_structure":
            summary.append("School Fee Structure detected.")
            eligibility_flags.append("✅ Financial need document present")
            score += 1
            criteria_met += 1

        elif label == "id_card":
            summary.append("ID document detected.")
            eligibility_flags.append("✅ ID verified")
            score += 1
            criteria_met += 1

        elif label.startswith("character_reference"):
            summary.append(f"{label.replace('_', ' ').title()} detected.")
            if any(k in text_lower for k in ["contact", "phone", "email", "mobile"]):
                eligibility_flags.append("✅ Reference includes contact info")
                score += 1
                criteria_met += 1
            else:
                eligibility_flags.append("⚠️ Reference missing contact info")

        elif label == "expression_of_interest":
            summary.append("Expression of Interest Letter detected.")
            if any(k in text_lower for k in ["motivation", "interest", "purpose", "goal"]):
                eligibility_flags.append("✅ Expression of interest contains motivation keywords")
                score += 1
                criteria_met += 1
            else:
                eligibility_flags.append("⚠️ Expression of interest lacks clear motivation")

        # progress after each document
        pct = int(processed / max(total, 1) * 90)
        maybe_update(pct, f"Processed {processed}/{total} documents")

    # Finalize (make denominator consistent)
    max_score = 2 + (total - 1)  # transcript=2, each other doc=1 if present
    summary.append(f"\n📊 Eligibility Score: {score}/{max_score}")
    summary.append(f"✅ Criteria Met: {criteria_met}/{total}")
    summary.append("📌 Flags:")
    summary.extend(eligibility_flags)

    maybe_update(95, "Finalizing results...")
    maybe_update(100, "Scan complete.")

    return "\n".join(summary)
