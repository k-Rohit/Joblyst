""" 
Extract plain text from the PDF,
The profile extraction will be done by an structured op LLM.
No OCR, no layout analysis (out of scope by design).
"""

from email.mime import text

from pypdf import PdfReader
from pathlib import Path
import logging

from joblyst.config import get_settings
from joblyst.exceptions import CVReadError

settings = get_settings()
logger = logging.getLogger(__name__)


def extract_cv_content(path: str | Path):
    """
    Return the concatenated text of a CV PDF.

    Raises ``CVReadError`` if the file is missing, unreadable, or empty of text
    (e.g. a scanned image with no text layer) so the caller can surface a clean
    message instead of an opaque parser traceback.
    """
    
    cv_path = Path(path)
    if not cv_path.exists():
        raise CVReadError("Path provided to extract the text from resume doesn't exist.")
    
    try:
        logger.info("Extracting text from PDF: %s", cv_path)
        reader = PdfReader(str(path))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as e:
        raise CVReadError(f"Could not read PDF {cv_path.name}: {e}") from e
    
    text = "\n".join(pages).strip()
    if not text:
        raise CVReadError(f"No extractable text in {cv_path.name}. Is it a scanned image? OCR is out of scope for this project.")
    return text
    




