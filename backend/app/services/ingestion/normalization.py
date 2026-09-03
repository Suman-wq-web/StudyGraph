"""
Text normalization/cleaning: the step between raw extracted content and
tokenization in the processing pipeline (see app/services/processing_service.py).
Collapses runs of blank lines and trims trailing whitespace left over from
pasted/typed content, without altering wording -- so chunk boundaries land on
real content rather than blank lines.

Pure and side-effect-free so it can be unit tested independently -- see
backend/tests/test_normalization.py.
"""


def normalize_text(text: str) -> str:
    lines = [line.strip() for line in text.splitlines()]

    collapsed: list[str] = []
    previous_blank = False
    for line in lines:
        if line:
            collapsed.append(line)
            previous_blank = False
        elif not previous_blank:
            collapsed.append("")
            previous_blank = True

    return "\n".join(collapsed).strip()
