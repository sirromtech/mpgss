from django.core.exceptions import ValidationError

def validate_upload(file, label):
    """
    Generic validator for uploaded files.
    Ensures file exists, is PDF, and under size limit.
    """
    if not file:
        raise ValidationError(f"{label} is required.")

    # Check file extension
    if not file.name.lower().endswith(".pdf"):
        raise ValidationError(f"{label} must be a PDF file.")

    # Check file size (example: 5 MB limit)
    if file.size > 5 * 1024 * 1024:
        raise ValidationError(f"{label} must be smaller than 5MB.")

    return file
