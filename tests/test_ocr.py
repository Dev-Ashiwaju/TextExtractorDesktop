import pytest
from PIL import Image

from textextractor.core import ocr
from textextractor.core.models import EngineUnavailable
from textextractor.core.ocr import (RapidOcrEngine, TesseractEngine, TextBox, blocks_to_result, layout_blocks,
                                    parse_tesseract_tsv, resolve_engine)

HEADER = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"


def row(level, b, p, l, w, conf, text):
    return f"{level}\t1\t{b}\t{p}\t{l}\t{w}\t0\t0\t10\t10\t{conf}\t{text}\n"


def test_blocks_to_result():
    r = blocks_to_result([["Line one", " Line two "], [], ["  "], ["Second block"]], "x")
    assert r.text == "Line one\nLine two\n\nSecond block"
    assert [b.text for b in r.blocks] == ["Line one\nLine two", "Second block"]
    assert blocks_to_result([]).is_empty
    assert blocks_to_result([["₦12,500.00", "Ref: INV-2024/001"]]).text == "₦12,500.00\nRef: INV-2024/001"


def test_parse_tsv_groups_words_lines_paragraphs():
    tsv = HEADER + row(1, 0, 0, 0, 0, -1, "") + row(4, 1, 1, 1, 0, -1, "") \
        + row(5, 1, 1, 1, 1, 96, "Hello") + row(5, 1, 1, 1, 2, 95, "world") \
        + row(5, 1, 1, 2, 1, 90, "second") + row(5, 1, 1, 2, 2, 91, "line") \
        + row(5, 2, 1, 1, 1, 88, "Next") + row(5, 2, 1, 1, 2, 88, "paragraph") \
        + row(5, 2, 1, 1, 3, -1, "ignored") + row(5, 2, 1, 1, 4, 80, "   ")
    r = parse_tesseract_tsv(tsv)
    assert r.text == "Hello world\nsecond line\n\nNext paragraph"
    assert len(r.blocks) == 2


def test_parse_tsv_keeps_text_with_special_characters():
    r = parse_tesseract_tsv(HEADER + row(5, 1, 1, 1, 1, 90, '"quoted"') + row(5, 1, 1, 1, 2, 90, "a\tb"))
    assert '"quoted"' in r.text


def test_parse_tsv_empty():
    assert parse_tesseract_tsv(HEADER).is_empty
    assert parse_tesseract_tsv("").is_empty


def test_layout_two_columns_and_paragraphs():
    boxes = [
        TextBox(40, 40, 360, 70, "Left one"), TextBox(640, 42, 990, 72, "Right one"),
        TextBox(40, 80, 360, 110, "Left two"), TextBox(640, 82, 990, 112, "Right two"),
        TextBox(40, 220, 360, 250, "Left new paragraph"),
    ]
    blocks = layout_blocks(boxes)
    assert blocks == [["Left one", "Left two"], ["Left new paragraph"], ["Right one", "Right two"]]


def test_layout_same_row_in_one_column_is_joined_left_to_right():
    boxes = [TextBox(300, 10, 500, 40, "world"), TextBox(10, 10, 280, 40, "hello"),
             TextBox(10, 50, 500, 80, "next line")]
    assert layout_blocks(boxes) == [["hello world", "next line"]]


def test_layout_empty():
    assert layout_blocks([]) == []
    assert layout_blocks([TextBox(0, 0, 1, 1, "  ")]) == []


def test_unavailable_engine_raises_with_hint(monkeypatch):
    eng = TesseractEngine(executable=None)
    eng._exe = None
    assert not eng.is_available()
    with pytest.raises(EngineUnavailable) as e:
        eng.recognize(Image.new("RGB", (10, 10)))
    assert "Tesseract" in str(e.value)


def test_resolve_engine_prefers_tesseract(monkeypatch):
    class Fake(ocr.OcrEngine):
        def __init__(self, ok): self.ok = ok
        def is_available(self): return self.ok
        def recognize(self, image, languages=("eng",)): ...
    monkeypatch.setattr(ocr, "_ENGINES", {"tesseract": Fake(True), "rapidocr": Fake(True)})
    assert resolve_engine("auto") is ocr._ENGINES["tesseract"]
    monkeypatch.setattr(ocr, "_ENGINES", {"tesseract": Fake(False), "rapidocr": Fake(True)})
    assert resolve_engine("auto") is ocr._ENGINES["rapidocr"]
    assert resolve_engine("tesseract") is ocr._ENGINES["tesseract"]  # explicit choice honoured


# ----------------------------------------------------------------- real engines
needs_tess = pytest.mark.skipif(not TesseractEngine().is_available(), reason="tesseract not installed")
needs_rapid = pytest.mark.skipif(not RapidOcrEngine().is_available(), reason="rapidocr not installed")
PARAGRAPH = ["Thank you for your purchase. Your order will be",
             "shipped within three business days. Please contact",
             "support@example.com if you have any questions."]


@pytest.mark.ocr
@needs_tess
@pytest.mark.parametrize("size,min_ratio", [(22, 1.0), (30, 1.0), (40, 0.97)])
def test_tesseract_reads_english_paragraph(render_text, size, min_ratio):
    """Exact at normal text sizes. Very large glyphs (40 px) are known to cost Tesseract a stray character
    (e.g. 'sSupport'), so that case only requires >= 97 % similarity."""
    import difflib
    r = TesseractEngine().recognize(render_text(PARAGRAPH, size=size))
    got, want = " ".join(r.text.split()), " ".join(PARAGRAPH)
    assert difflib.SequenceMatcher(None, got, want).ratio() >= min_ratio
    if min_ratio == 1.0:
        assert got == want
    assert r.engine == "Tesseract" and r.elapsed > 0


@pytest.mark.ocr
@needs_tess
def test_tesseract_blank_image_is_empty():
    assert TesseractEngine().recognize(Image.new("RGB", (600, 400), "white")).is_empty


@pytest.mark.ocr
@needs_tess
def test_tesseract_numbers_dates_and_symbols(render_text):
    r = TesseractEngine().recognize(render_text(["Invoice INV-2024/001", "Total: 12,500.00", "Date: 15 March 2024"]))
    assert "INV-2024/001" in r.text and "12,500.00" in r.text and "15 March 2024" in r.text


@pytest.mark.ocr
@needs_tess
def test_tesseract_separates_paragraphs(render_text):
    img = render_text(["First paragraph line one", "First paragraph line two", "", "", "Second paragraph here"], size=34)
    r = TesseractEngine().recognize(img)
    assert len(r.blocks) == 2
    assert r.blocks[1].text.startswith("Second")


@pytest.mark.ocr
@needs_tess
def test_tesseract_handles_small_image_by_upscaling(render_text):
    r = TesseractEngine().recognize(render_text(["Small text"], size=14, width=200))
    assert "Small" in r.text


@pytest.mark.ocr
@needs_tess
def test_tesseract_lists_languages_and_ignores_unknown_ones(render_text):
    eng = TesseractEngine()
    assert "eng" in eng.languages()
    assert "Hello" in eng.recognize(render_text(["Hello"]), languages=("zzz", "eng")).text


@pytest.mark.ocr
@needs_tess
def test_tesseract_reads_dark_theme_screenshot(render_text):
    r = TesseractEngine().recognize(render_text(["Dark mode screenshot text"], bg="#1e1e1e", fg="#e6e6e6"))
    assert "Dark mode" in r.text


@pytest.mark.ocr
@needs_rapid
def test_rapidocr_recognizes_text_and_blank(render_text):
    eng = RapidOcrEngine()
    r = eng.recognize(render_text(["Invoice 2024 total 1250"], size=44))
    assert "1250" in r.text.replace(" ", "")
    assert eng.recognize(Image.new("RGB", (600, 400), "white")).is_empty
