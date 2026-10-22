from textextractor.core.text_tools import char_count, detect_entities, find_all, word_count


def test_word_and_char_counts():
    assert word_count("") == 0
    assert word_count("  \n\t ") == 0
    assert word_count("Hello   world\nthis is\n\nedited") == 5
    assert char_count("Hello world") == 11


def test_find_all_case_insensitive_non_overlapping():
    assert find_all("Total: 10. total again, TOTAL", "total") == [(0, 5), (11, 16), (24, 29)]
    assert find_all("aaaa", "aa") == [(0, 2), (2, 4)]
    assert find_all("hello", "") == []
    assert find_all("hello", "xyz") == []


def test_find_all_treats_query_literally():
    assert find_all("price (USD) 5.00", "(usd)") == [(6, 11)]
    assert find_all("a.b", ".") == [(1, 2)]


def test_detects_urls_emails_phones():
    text = "Visit https://example.com/path?x=1, mail ola@example.org or call +234 801 234 5678."
    found = detect_entities(text)
    assert any(e.kind == "url" and e.value == "https://example.com/path?x=1" for e in found)
    assert any(e.kind == "email" and e.value == "ola@example.org" for e in found)
    assert any(e.kind == "phone" and e.value.startswith("+234") for e in found)


def test_entity_edge_cases():
    assert [e.value for e in detect_entities("See (www.example.com).") if e.kind == "url"] == ["www.example.com"]
    assert not [e for e in detect_entities("Invoice date 2024-01-15 and 15/01/2024") if e.kind == "phone"]
    assert not [e for e in detect_entities("https://example.com/12345678901") if e.kind == "phone"]
    assert detect_entities("Total 1,250.00 NGN, qty 12") == []
    assert len([e for e in detect_entities("a@b.com and again a@b.com") if e.kind == "email"]) == 1
    assert detect_entities("") == []
