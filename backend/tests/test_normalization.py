from app.services.ingestion.normalization import normalize_text


def test_empty_string_stays_empty():
    assert normalize_text("") == ""


def test_whitespace_only_becomes_empty():
    assert normalize_text("   \n\n\t  ") == ""


def test_trims_trailing_whitespace_per_line():
    assert normalize_text("hello   \nworld\t\t\n") == "hello\nworld"


def test_collapses_multiple_blank_lines_to_one():
    text = "Paragraph one.\n\n\n\n\nParagraph two."
    assert normalize_text(text) == "Paragraph one.\n\nParagraph two."

    # a lone blank line is preserved as a paragraph separator, not stripped entirely
    assert "\n\n" in normalize_text(text)


def test_already_clean_text_is_unchanged():
    text = "Line one.\n\nLine two.\n\nLine three."
    assert normalize_text(text) == text


def test_leading_and_trailing_blank_lines_are_removed():
    assert normalize_text("\n\n\nhello\n\n\n") == "hello"
