"""
Property-based test: Prescription filename sanitization removes unsafe characters.

Property 6: For any patient name string, the filename produced by the
prescription service SHALL contain only alphanumeric characters and underscores,
and SHALL NOT contain spaces, slashes, or other filesystem-unsafe characters.

The resulting filename must match the regex ``^[a-zA-Z0-9_]+\\.pdf$``.

Validates: Requirements 8.6
"""
import re

from hypothesis import assume, given, settings, HealthCheck
from hypothesis import strategies as st

from app.pdf_service import sanitize_patient_name

# ---------------------------------------------------------------------------
# Regex that the full filename must satisfy
# ---------------------------------------------------------------------------

FILENAME_RE = re.compile(r"^[a-zA-Z0-9_]+\.pdf$")


# ---------------------------------------------------------------------------
# Property-based test
# ---------------------------------------------------------------------------


@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
@given(patient_name=st.text())
def test_filename_sanitization_removes_unsafe_characters(patient_name: str):
    """
    **Validates: Requirements 8.6**

    Property 6: Prescription filename sanitization removes unsafe characters.

    For any arbitrary Unicode string used as a patient name, the filename
    constructed by the prescription service SHALL match ``^[a-zA-Z0-9_]+\\.pdf$``.

    This means:
    - The filename contains ONLY alphanumeric characters and underscores
      (plus the literal ".pdf" extension).
    - No spaces, hyphens, slashes, Unicode characters, or other
      filesystem-unsafe characters appear in the filename.
    - The filename is never empty (the sanitizer falls back to "patient"
      when all characters are stripped).
    """
    safe_name = sanitize_patient_name(patient_name)
    filename = f"prescription_{safe_name}.pdf"

    assert FILENAME_RE.match(filename), (
        f"Filename {filename!r} does not match {FILENAME_RE.pattern!r}. "
        f"Input patient_name={patient_name!r}, safe_name={safe_name!r}"
    )
