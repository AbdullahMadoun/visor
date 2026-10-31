"""Perception without a browser: layout, matching and caching on synthetic OCR boxes."""
import os

import cv2
import numpy as np
import pytest

from visor.core import ocr


def box(text, x1, y1, x2, y2, conf=1.0):
    return (text, conf, x1, y1, x2, y2)


def layout(*boxes):
    return ocr._layout(list(boxes), 1.0)


def test_word_gaps_split_a_line_into_phrases():
    items = layout(box("Home", 10, 10, 50, 30), box("About", 80, 10, 125, 30), box("us", 128, 10, 145, 30),
                   box("Pricing", 175, 10, 230, 30))
    assert [it["text"] for it in items] == ["Home", "About us", "Pricing"]
    assert {it["line"] for it in items} == {0}


def test_lines_are_read_top_to_bottom():
    items = layout(box("Second", 10, 60, 80, 80), box("First", 10, 10, 70, 30))
    assert [it["text"] for it in items] == ["First", "Second"]
    assert [it["order"] for it in items] == [0, 1]


def test_word_inside_a_merged_line_is_located_precisely():
    # Vision often returns a whole nav bar as one box
    items = layout(box("Home About us", 0, 0, 130, 20))
    m = ocr.find_matches("About", items=items)[0]
    assert m["tier"] == 4 and m["text"] == "About"
    assert 50 <= m["x"] <= 90  # "About" spans characters 5-10 of 13


def test_arabic_reads_right_to_left_and_folds_letter_variants():
    items = layout(box("التسوق", 800, 10, 850, 30), box("عربة", 860, 10, 890, 30),
                   box("إلى", 896, 10, 920, 30), box("أضف", 925, 10, 960, 30))
    assert items[0]["text"] == "أضف إلى عربة التسوق"
    m = ocr.find_matches("اضف الى عربه", items=items)[0]
    assert m["tier"] == 4 and m["x"] > 880  # the right-hand words


def test_cjk_tokens_join_without_spaces():
    assert layout(box("购", 10, 10, 26, 30), box("物", 27, 10, 43, 30))[0]["text"] == "购物"


def test_normalize():
    assert ocr.normalize("  Sign-In!  ") == "sign in"
    assert ocr.normalize("Ｃａｒｔ（3）") == "cart 3"
    assert ocr.normalize("أَهْلاً") == ocr.normalize("اهلا")


@pytest.mark.parametrize("label,text,tier", [
    ("Login", "Login", 5),
    ("sign up", "Sign-up", 5),       # punctuation ignored
    ("Signup", "Sign up", 5),        # OCR splitting / joining words
    ("Login", "Home Login", 4),
    ("cart", "Cart(3)", 3),
    ("check", "checkout", 2),
    ("Settings", "Setings", 1),      # OCR misread
])
def test_match_tiers(label, text, tier):
    items = layout(box(text, 0, 0, 10 * len(text), 20))
    assert ocr.find_matches(label, items=items)[0]["tier"] == tier


def test_exact_mode_ignores_words_in_body_text():
    items = layout(box("Connect with people you know on the site", 0, 0, 400, 20))
    assert ocr.find_matches("Connect", items=items, exact=True) == []
    assert ocr.find_matches("Connect", items=items, exact=False)


def test_short_phrase_ranks_above_sentence():
    items = layout(box("Click checkout when your cart is ready", 0, 0, 380, 20),
                   box("Checkout", 0, 50, 80, 70))
    assert ocr.find_matches("checkout", items=items)[0]["phrase"] == "Checkout"


def test_short_labels_are_never_fuzzy():
    items = layout(box("play", 0, 0, 40, 20))
    assert ocr.find_matches("pay", items=items) == []


def test_pick_by_index_and_near():
    items = layout(box("Add to cart", 10, 100, 110, 120), box("Add to cart", 300, 100, 400, 120))
    matches = ocr.find_matches("Add to cart", items=items)
    assert ocr._pick(matches, index=1)["x"] > 300
    assert ocr._pick(matches, near=(320, 80))["x"] > 300
    assert ocr._pick(matches, index=5) is None


def test_bounds_accept_both_dict_shapes():
    m = {"x": 50, "y": 50}
    assert ocr._in_bounds(m, {"x": 0, "y": 0, "w": 100, "h": 100})
    assert ocr._in_bounds(m, {"x": 0, "y": 0, "width": 100, "height": 100})
    assert not ocr._in_bounds(m, (60, 0, 100, 100))


def test_score_match_kept_for_old_callers():
    assert ocr._score_match("Submit", "submit", True) == (3, 1.0)
    assert ocr._score_match("play", "pay", False) == (0, 0.0)


@pytest.fixture
def fake_engine(monkeypatch, tmp_path):
    calls = []

    def engine(img_path, data, w, h):
        calls.append(img_path)
        return [box("Hello world", 10, 10, 120, 30)]

    monkeypatch.setattr(ocr, "_engine_boxes", engine)
    monkeypatch.setattr(ocr, "get_reader", lambda: None)
    img = str(tmp_path / "screen.png")
    cv2.imwrite(img, np.full((100, 200, 3), 255, np.uint8))
    ocr.register_capture(img, 1.0)
    return img, calls


def test_ocr_runs_once_per_distinct_image(fake_engine):
    img, calls = fake_engine
    first = ocr.find_all(img)
    first[0]["text"] = "mutated by caller"
    assert ocr.find_all(img)[0]["text"] == "Hello world"  # cache returns copies
    assert len(calls) == 1


def test_missing_or_unreadable_image_gives_no_text(tmp_path):
    assert ocr.find_all(str(tmp_path / "nope.png")) == []
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image")
    assert ocr.find_all(str(bad)) == []


def test_registered_scale_wins_and_expires_on_rewrite(tmp_path):
    img = str(tmp_path / "s.png")
    cv2.imwrite(img, np.zeros((10, 20, 3), np.uint8))
    ocr.register_capture(img, 2.0)
    assert ocr._registered_scale(img) == 2.0
    os.utime(img, ns=(1, 1))  # file rewritten by someone else
    assert ocr._registered_scale(img) is None


def test_numbers_keep_their_separators():
    from visor.core import ocr
    item = {"text": "Posted Oct 23, 2023", "confidence": 1.0, "x": 0, "y": 0, "x1": 0, "y1": 0, "x2": 1, "y2": 1}
    assert ocr.find_matches("2/3", items=[item]) == []
    step = dict(item, text="Step 2/3")
    assert ocr.find_matches("2/3", items=[step])


def test_proof_needs_whole_words():
    from visor.core import ocr
    def tiers(label, text):
        item = {"text": text, "confidence": 1.0, "x": 0, "y": 0, "x1": 0, "y1": 0, "x2": 1, "y2": 1}
        return [m["tier"] for m in ocr.find_matches(label, items=[item])]
    assert all(t < ocr.PROOF_TIER for t in tiers("Saved", "Save"))     # fuzzy look-alike
    assert all(t < ocr.PROOF_TIER for t in tiers("Sent", "Unsent"))    # part of another word
    assert max(tiers("Sent", "Message sent")) >= ocr.PROOF_TIER
