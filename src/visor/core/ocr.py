"""
Perception — what text is on screen, and where.

Pipeline: OCR engine → word boxes → lines → phrases (one per button, link or
run of text) → matching. Matching works on word spans inside each phrase, so
"About" is clicked precisely even when OCR returns "Home About us" as one line.
All coordinates returned are CSS pixels of the page, ready for clicking.
"""
import os
import re
import sys
import uuid
import time
import difflib
import hashlib
import unicodedata
from collections import OrderedDict
from typing import Optional

import cv2
import numpy as np

from visor.core import WORKSPACE_DIR
from visor.config import settings

_reader = None
_use_ocrmac = False
_engine = None  # "livetext" | "vision" | "easyocr"

# Short language codes → the identifiers Apple's OCR expects
_APPLE_LANGS = {
    "en": "en-US", "ar": "ar-SA", "fr": "fr-FR", "de": "de-DE", "es": "es-ES", "it": "it-IT",
    "pt": "pt-BR", "zh": "zh-Hans", "ja": "ja-JP", "ko": "ko-KR", "ru": "ru-RU", "uk": "uk-UA",
}


def _hide_dock_icon():
    """Apple's OCR loads AppKit, which makes every Python process that reads the screen show up
    in the Dock. Visor is a background tool: tell macOS so (VISOR_DOCK_ICON=1 keeps the icon)."""
    if os.environ.get("VISOR_DOCK_ICON") == "1":
        return
    try:
        from AppKit import NSApplication, NSApplicationActivationPolicyProhibited
        NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyProhibited)
    except Exception:
        pass


def get_reader():
    global _reader, _use_ocrmac, _engine
    if _reader is None:
        wanted = (settings.ocr_engine or "auto").lower()
        try:
            if sys.platform == 'darwin' and wanted != "easyocr":
                from ocrmac import ocrmac
                _hide_dock_icon()
                print("[OCR] Successfully loaded native Apple Vision API (ocrmac). Lightning fast mode enabled.")
                _reader = ocrmac
                _use_ocrmac = True
                # LiveText gives word boxes and reads Arabic/CJK out of the box; Vision is the fallback
                _engine = "vision" if wanted == "vision" else "livetext"
                return _reader
        except ImportError:
            pass

        print("[OCR] ocrmac not found or incompatible. Falling back to EasyOCR (GPU/MPS)...")
        import easyocr
        langs = settings.ocr_langs or os.environ.get("EASYOCR_LANGS", "en").split(",")
        _reader = easyocr.Reader(langs, gpu=True)
        _use_ocrmac = False
        _engine = "easyocr"
    return _reader


# ── Scale (image pixels → CSS pixels) ────────────────────────────────────────

_capture_scales = {}  # abs path → (mtime_ns, scale), recorded when visor took the screenshot


def register_capture(img_path: str, scale: float):
    """Remember the image/CSS scale of a screenshot visor just took."""
    try:
        _capture_scales[os.path.abspath(img_path)] = (os.stat(img_path).st_mtime_ns, float(scale))
    except OSError:
        pass


def _registered_scale(img_path: str) -> Optional[float]:
    entry = _capture_scales.get(os.path.abspath(img_path)) if img_path else None
    try:
        if entry and os.stat(img_path).st_mtime_ns == entry[0]:
            return entry[1]
    except OSError:
        pass
    return None


def _resolve_scale_factor(img_w: int, page=None, img_path: str = None) -> float:
    """
    Safely resolves the scale factor without triggering an unintended browser launch.
    Uses the scale recorded when visor took the screenshot; otherwise derives it from
    screenshot width vs the CSS width of the page that took it (else visor's own page).
    """
    registered = _registered_scale(img_path)
    if registered:
        return registered
    if page is None:
        from visor.core import browser
        page = browser._page
    if page is not None:
        try:
            if not page.is_closed():
                vp = page.viewport_size
                css_w = vp["width"] if vp and vp.get("width") else page.evaluate("window.innerWidth")
                if css_w:
                    return min(4.0, max(0.25, round(img_w / float(css_w), 2)))
                return float(page.evaluate("window.devicePixelRatio"))
        except Exception:
            pass
    # No live page to measure: assume Retina on macOS (ocrmac), 1x elsewhere
    return 2.0 if _use_ocrmac else 1.0


# ── Engine ───────────────────────────────────────────────────────────────────

def _image_size(data: bytes) -> tuple:
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    return (img.shape[1], img.shape[0]) if img is not None else (0, 0)


def _engine_boxes(img_path: str, data: bytes, w_img: int, h_img: int) -> list:
    """Run OCR. Returns (text, confidence, x1, y1, x2, y2) in image pixels, top-left origin."""
    global _engine
    reader = get_reader()
    if _use_ocrmac:
        langs = [_APPLE_LANGS.get(lang.lower(), lang) for lang in settings.ocr_langs] or None
        if _engine == "livetext":
            try:
                results = reader.OCR(img_path, framework="livetext", language_preference=langs,
                                     unit="token").recognize()
            except Exception as e:  # macOS < 13 or an ocrmac without LiveText
                print(f"[OCR] LiveText unavailable ({e}). Using Vision instead.")
                _engine = "vision"
                return _engine_boxes(img_path, data, w_img, h_img)
        else:
            results = reader.OCR(img_path, language_preference=langs).recognize()
        boxes = []
        # ocrmac returns: (text, confidence, [x, y, w, h]) where coordinates are ratios (0-1)
        # Note: Origin (0,0) in ocrmac bounding boxes is bottom-left!
        for text, conf, (bx, by, bw, bh) in results:
            if conf < 0.1:
                continue
            y_max = h_img - by * h_img
            boxes.append((text, float(conf), bx * w_img, y_max - bh * h_img, (bx + bw) * w_img, y_max))
        return boxes

    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    boxes = []
    for bbox, text, prob in reader.readtext(img):
        xs = [p[0] for p in bbox]
        ys = [p[1] for p in bbox]
        boxes.append((text, float(prob), min(xs), min(ys), max(xs), max(ys)))
    return boxes


# ── Layout: words → lines → phrases ──────────────────────────────────────────

_RTL_CHARS = re.compile(r"[֐-ࣿיִ-﷿ﹰ-ﻼ]")
_CJK_CHARS = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯]")


def _is_rtl(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return bool(letters) and 2 * sum(1 for c in letters if _RTL_CHARS.match(c)) > len(letters)


def _word(text, conf, x1, y1, x2, y2) -> dict:
    return {"text": text, "confidence": conf, "x1": x1, "y1": y1, "x2": x2, "y2": y2}


def _split_words(text, conf, x1, y1, x2, y2) -> list:
    """Split one OCR box into word boxes, sizing each word by its share of the characters."""
    text = text.strip()
    parts = [(m.start(), m.end(), m.group()) for m in re.finditer(r"\S+", text)]
    if len(parts) <= 1:
        return [_word(text, conf, x1, y1, x2, y2)] if text else []
    total, width, rtl = float(len(text)), x2 - x1, _is_rtl(text)
    words = []
    for start, end, part in parts:
        if rtl:  # the first character sits at the right edge
            words.append(_word(part, conf, x2 - width * end / total, y1, x2 - width * start / total, y2))
        else:
            words.append(_word(part, conf, x1 + width * start / total, y1, x1 + width * end / total, y2))
    return words


def _group_lines(words: list) -> list:
    """Cluster words whose vertical centres line up into lines, top to bottom."""
    lines = []
    for w in sorted(words, key=lambda w: ((w["y1"] + w["y2"]) / 2, w["x1"])):
        cy, h = (w["y1"] + w["y2"]) / 2, max(1.0, w["y2"] - w["y1"])
        for line in reversed(lines[-4:]):
            if abs(cy - line["cy"]) <= 0.5 * min(h, line["h"]):
                line["words"].append(w)
                n = len(line["words"])
                line["cy"] += (cy - line["cy"]) / n
                line["h"] += (h - line["h"]) / n
                break
        else:
            lines.append({"cy": cy, "h": h, "words": [w]})
    lines.sort(key=lambda line: line["cy"])
    return lines


def _split_phrases(words: list) -> list:
    """Split a line where the gap between words is wider than a word space (separate UI elements)."""
    ws = sorted(words, key=lambda w: w["x1"])
    heights = sorted(w["y2"] - w["y1"] for w in ws)
    h = heights[len(heights) // 2] or 1.0
    phrases = [[ws[0]]]
    for prev, cur in zip(ws, ws[1:]):
        if cur["x1"] - prev["x2"] > 0.9 * h:
            phrases.append([cur])
        else:
            phrases[-1].append(cur)
    return phrases


def _join(words: list) -> str:
    out = ""
    for w in words:
        t = w["text"]
        if out and not (_CJK_CHARS.match(out[-1]) and _CJK_CHARS.match(t[:1])):
            out += " "
        out += t
    return out


def _layout(boxes: list, scale: float) -> list:
    """Turn raw OCR boxes into phrase items in reading order, scaled to CSS pixels."""
    words = []
    for text, conf, x1, y1, x2, y2 in boxes:
        words.extend(_split_words(text, conf, x1 / scale, y1 / scale, x2 / scale, y2 / scale))
    items = []
    for line_no, line in enumerate(_group_lines(words)):
        phrases = _split_phrases(line["words"])
        if _is_rtl(" ".join(w["text"] for w in line["words"])):
            phrases.reverse()
        for phrase in phrases:
            if _is_rtl(" ".join(w["text"] for w in phrase)):
                phrase = sorted(phrase, key=lambda w: -w["x2"])
            x1, y1 = min(w["x1"] for w in phrase), min(w["y1"] for w in phrase)
            x2, y2 = max(w["x2"] for w in phrase), max(w["y2"] for w in phrase)
            items.append({
                "text": _join(phrase),
                "x": int((x1 + x2) / 2), "y": int((y1 + y2) / 2),
                "x1": int(x1), "y1": int(y1), "x2": int(x2), "y2": int(y2),
                "confidence": round(sum(w["confidence"] for w in phrase) / len(phrase), 3),
                "line": line_no,
                "order": len(items),
                "words": [{"text": w["text"], "norm": normalize(w["text"]),
                           "x1": int(w["x1"]), "y1": int(w["y1"]),
                           "x2": int(w["x2"]), "y2": int(w["y2"])} for w in phrase],
            })
    return items


# ── Public perception API ────────────────────────────────────────────────────

_ocr_cache = OrderedDict()  # (image digest, scale, engine) → items
_CACHE_SIZE = 24


def find_all(img_path: str, page=None) -> list:
    """
    Run OCR on image, return all found text with positions, one item per phrase
    (button, link, run of text) in reading order.
    Returns list of: {text, x, y, x1, y1, x2, y2, confidence, line, order, words}
    """
    try:
        with open(img_path, "rb") as f:
            data = f.read()
    except (OSError, TypeError):
        return []
    w_img, h_img = _image_size(data)
    if not w_img:
        return []

    get_reader()
    scale_factor = _resolve_scale_factor(w_img, page, img_path)
    key = (hashlib.blake2b(data, digest_size=16).hexdigest(), scale_factor, _engine)
    if key in _ocr_cache:  # same pixels already read (e.g. polling a static screen)
        _ocr_cache.move_to_end(key)
        return [dict(item) for item in _ocr_cache[key]]

    try:
        boxes = _engine_boxes(img_path, data, w_img, h_img)
    except Exception as e:
        print(f"[OCR] Could not read {img_path}: {e}")
        return []
    items = _layout(boxes, scale_factor)
    _ocr_cache[key] = items
    while len(_ocr_cache) > _CACHE_SIZE:
        _ocr_cache.popitem(last=False)
    return [dict(item) for item in items]


def lines(img_path: str, page=None) -> list:
    """Visible text as lines, top to bottom (phrases on one line joined by wide gaps)."""
    grouped = OrderedDict()
    for item in find_all(img_path, page):
        grouped.setdefault(item["line"], []).append(item["text"])
    return ["   ".join(parts) for parts in grouped.values()]


# ── Matching ─────────────────────────────────────────────────────────────────

_ARABIC_MARKS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")  # harakat, tatweel
_ARABIC_FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي"})


def normalize(text: str) -> str:
    """Comparison form of text: case-folded, punctuation as spaces, Arabic letter variants folded."""
    text = unicodedata.normalize("NFKC", text or "").casefold()
    text = _ARABIC_MARKS.sub("", text).translate(_ARABIC_FOLD)
    out = []
    for c in text:
        cat = unicodedata.category(c)
        if cat == "Cf":  # zero-width joiners etc.
            continue
        out.append(" " if cat[0] in "PSZ" or cat == "Cc" else c)
    return " ".join("".join(out).split())


def _contains_words(words: list, sub: list) -> bool:
    n = len(sub)
    return any(words[i:i + n] == sub for i in range(len(words) - n + 1))


# Lowest tier that counts as proof that text is on screen (goals, expect=). A fuzzy
# match lets "Save" pass for "Saved", and a substring lets "Unsent" pass for "Sent".
PROOF_TIER = 3


def _phrase_spans(item: dict, label_norm: str, label_words: list, label_compact: str, exact: bool):
    """Yield (tier, ratio, start, end) for word spans of a phrase that match the label.

    Tier 5: the whole phrase is the label (an isolated button or link)
    Tier 4: the label is a run of words inside the phrase (shorter phrases rank higher)
    Tier 3: the label is part of one OCR token ("Cart(3)")
    Tier 2: the label is a substring of a word (exact=False only)
    Tier 1: fuzzy match for OCR misreads (labels longer than 4 characters)
    Tiers 1-2 can aim a click, but never prove a result (see PROOF_TIER).
    """
    words = item.get("words") or [{"text": item["text"]}]
    norms = [w["norm"] if "norm" in w else normalize(w["text"]) for w in words]
    n = len(label_words)
    phrase_len = sum(len(t.split()) for t in norms) or 1
    # "2/3" is not "23" and not inside "2023": with digits, the gaps between words matter
    joinable = not any(c.isdigit() for c in label_compact)
    for i in range(len(words)):
        for j in range(i + 1, min(len(words), i + n + 1) + 1):
            span = " ".join(t for t in norms[i:j] if t)
            if not span:
                continue
            compact = span.replace(" ", "")
            if span == label_norm or (joinable and compact == label_compact):
                if i == 0 and j == len(words):
                    yield (5, 1.0, i, j)
                elif not exact or phrase_len <= n + 3:  # exact mode: only short phrases, not body text
                    yield (4, min(1.0, n / phrase_len), i, j)  # shorter phrase = more button-like
                continue
            if j - i == 1 and _contains_words(span.split(), label_words) and (not exact or len(span.split()) <= n + 1):
                yield (3, len(label_compact) / len(compact), i, j)
                continue
            if not exact and joinable and j - i <= n and label_compact in compact:
                yield (2, len(label_compact) / len(compact), i, j)
                continue
            if len(label_compact) > 4 and abs((j - i) - n) <= 1:
                threshold = 0.90 if exact else 0.80
                sm = difflib.SequenceMatcher(None, compact, label_compact)
                # cheap upper bounds first; the full ratio is the slow part
                if sm.real_quick_ratio() >= threshold and sm.quick_ratio() >= threshold:
                    ratio = sm.ratio()
                    if ratio >= threshold:
                        yield (1, ratio, i, j)


def _span_match(item: dict, start: int, end: int, tier: int, ratio: float) -> dict:
    words = (item.get("words") or [item])[start:end]
    x1, y1 = min(w["x1"] for w in words), min(w["y1"] for w in words)
    x2, y2 = max(w["x2"] for w in words), max(w["y2"] for w in words)
    return {
        "text": _join(words) if item.get("words") else item["text"],
        "x": int((x1 + x2) / 2), "y": int((y1 + y2) / 2),
        "x1": x1, "y1": y1, "x2": x2, "y2": y2,
        "confidence": item["confidence"],
        "phrase": item["text"], "line": item.get("line", 0), "order": item.get("order", 0),
        "start": start, "tier": tier, "ratio": round(ratio, 3),
    }


def find_matches(label: str, img_path: str = None, exact: bool = False, min_conf: float = 0.6,
                 page=None, items: list = None) -> list:
    """Every place `label` appears on screen, best match first."""
    if items is None:
        items = find_all(img_path, page)
    label_norm = normalize(label)
    if not label_norm:
        return []
    label_words, label_compact = label_norm.split(), label_norm.replace(" ", "")
    matches = []
    for item in items:
        if item["confidence"] < min_conf:
            continue
        spans = sorted(_phrase_spans(item, label_norm, label_words, label_compact, exact),
                       key=lambda s: (-s[0], -s[1]))
        taken = []
        for tier, ratio, i, j in spans:
            if any(i < b and a < j for a, b in taken):  # keep the best non-overlapping spans
                continue
            taken.append((i, j))
            matches.append(_span_match(item, i, j, tier, ratio))
    # Hierarchy: tier, similarity, OCR confidence, then reading order (top-left first)
    matches.sort(key=lambda m: (-m["tier"], -m["ratio"], -m["confidence"], m["order"], m["start"]))
    return matches


def _in_bounds(m: dict, bounds) -> bool:
    if isinstance(bounds, dict):
        bx, by = bounds["x"], bounds["y"]
        bw, bh = bounds.get("w", bounds.get("width")), bounds.get("h", bounds.get("height"))
        return bx <= m["x"] <= bx + bw and by <= m["y"] <= by + bh
    x1, y1, x2, y2 = bounds
    return x1 <= m["x"] <= x2 and y1 <= m["y"] <= y2


def _pick(matches: list, near=None, index: int = None) -> Optional[dict]:
    """Choose among the best-tier matches: nearest to `near`, or the index-th in reading order."""
    best_tier = [m for m in matches if m["tier"] == matches[0]["tier"]]
    if near is not None:
        nx, ny = near
        return min(best_tier, key=lambda m: (m["x"] - nx) ** 2 + (m["y"] - ny) ** 2)
    if index is not None:
        ordered = sorted(best_tier, key=lambda m: (m["order"], m["start"]))
        return ordered[index] if -len(ordered) <= index < len(ordered) else None
    return matches[0]


def _score_match(candidate_text: str, target: str, exact: bool) -> tuple:
    """
    Hierarchical match scoring of two whole strings (kept for callers of the old API):
    Tier 3: Identical string match (ratio = 1.0)
    Tier 2: Substring containment (ratio = len(tgt)/len(cand))
    Tier 1: High-confidence fuzzy match (disabled for short words <= 4 chars)
    Tier 0: No match (0, 0.0)
    """
    cand = candidate_text.lower().strip()
    tgt = target.lower().strip()

    if not cand or not tgt:
        return (0, 0.0)

    # Tier 3: Identical match
    if cand == tgt:
        return (3, 1.0)

    # Tier 2: Substring containment
    if not exact and tgt in cand:
        return (2, len(tgt) / float(len(cand)))

    # Prevent false positives on short words (e.g. 'pay' matching 'play', 'close' matching 'clone')
    if len(tgt) <= 4:
        return (0, 0.0)

    # Tier 1: Fuzzy matching with strict threshold
    ratio = difflib.SequenceMatcher(None, cand, tgt).ratio()
    threshold = 0.90 if exact else 0.85
    if ratio >= threshold:
        return (1, ratio)

    if not exact and len(tgt.split()) == 1:
        for w in cand.split():
            if len(w) > 4 and difflib.SequenceMatcher(None, w, tgt).ratio() >= 0.85:
                return (1, 0.85)

    return (0, 0.0)


def find(label: str, img_path: str, exact: bool = True,
         min_conf: float = 0.6,
         bounds: dict = None, page=None, near=None, index: int = None) -> Optional[dict]:
    """
    Find a label in the screenshot — geometrically and hierarchically ranked.
    Exact matches outrank fuzzy matches regardless of OCR confidence score.
    bounds: {x, y, w, h} (or Playwright's {x, y, width, height}) to search inside.
    near:   (x, y) — among equally good matches, take the closest.
    index:  among equally good matches, take the index-th in reading order.
    """
    scored = find_matches(label, img_path, exact=exact, min_conf=min_conf, page=page)

    # Apply DOM bounds constraint if specified
    if bounds:
        scored = [m for m in scored if _in_bounds(m, bounds)]
        if not scored:
            print(f"[OCR] '{label}' not found within specified DOM bounds.")
            return None

    if not scored:
        return None

    best = _pick(scored, near=near, index=index)
    if best:
        print(f"[OCR] Found '{label}' (tier={best['tier']}, conf={best['confidence']}) at x={best['x']}, y={best['y']}")
    return best


def find_near(label: str, img_path: str, near_x: int, near_y: int,
              radius: int = 150, exact: bool = True, min_conf: float = 0.7,
              page=None) -> Optional[dict]:
    """
    Find label within a radius of a known (x, y) point (e.g. inside a newly opened dropdown).
    """
    candidates = []
    for m in find_matches(label, img_path, exact=exact, min_conf=min_conf, page=page):
        dist = ((m["x"] - near_x) ** 2 + (m["y"] - near_y) ** 2) ** 0.5
        if dist <= radius:
            candidates.append((m["tier"], dist, m))

    if not candidates:
        return None

    # Prefer highest match tier, then shortest distance
    candidates.sort(key=lambda c: (-c[0], c[1]))
    return candidates[0][2]


def summarize(img_path: str, page=None) -> list:
    """Return all found text strings for agent analysis."""
    return [item["text"] for item in find_all(img_path, page)]


def find_with_scroll(label: str, page, max_scrolls: int = 5, exact: bool = False, min_conf: float = 0.6) -> Optional[dict]:
    """
    Auto-scroll discovery engine.
    Pages down and searches iteratively until the target is found or the page stops moving.
    """
    os.makedirs(os.path.join(WORKSPACE_DIR, "logs"), exist_ok=True)
    previous = None
    for i in range(max_scrolls + 1):
        img_path = os.path.join(WORKSPACE_DIR, "logs", f"scroll_scan_{i}.png")
        page.screenshot(path=img_path)
        match = find(label, img_path, exact=exact, min_conf=min_conf, page=page)
        if match:
            print(f"[OCR-SCROLL] Found '{label}' after {i} scrolls at ({match['x']}, {match['y']}).")
            return match

        seen = summarize(img_path, page)
        if seen == previous:
            print(f"[OCR-SCROLL] Reached the end of the page; '{label}' not found.")
            return None
        previous = seen

        if i < max_scrolls:
            print(f"[OCR-SCROLL] '{label}' not found on screen {i}. Scrolling down...")
            page.mouse.wheel(0, 600)
            page.wait_for_timeout(1500)

    print(f"[OCR-SCROLL] '{label}' not found after {max_scrolls} scrolls.")
    return None


SEMANTIC_REGISTRY = {
    "cart": ["cart", "basket", "checkout", "عربة", "أضف إلى عربة"],
    "search": ["search", "find", "looking for", "بحث", "ابحث"],
    "english": ["english", "eng"]
}

def semantic_find(query: str, img_path: str, min_conf: float = 0.6, custom_dict: dict = None,
                  page=None) -> Optional[dict]:
    """
    Semantic mapping for multi-lingual/obfuscated UIs.
    Maps an abstract query like 'cart' to localized bounding boxes.
    """
    active_dict = dict(SEMANTIC_REGISTRY)
    if custom_dict:
        for k, v in custom_dict.items():
            norm_key = k.lower().strip()
            active_dict[norm_key] = [v] if isinstance(v, str) else list(v)

    target_list = active_dict.get(query.lower().strip(), [query])
    for target in target_list:
        # Substring matching stays on so 'cart' still hits 'Add to Cart';
        # fuzzy matching is already off for short words.
        match = find(target, img_path, exact=False, min_conf=min_conf, page=page)
        if match:
            print(f"[OCR-SEMANTIC] Mapped semantic intent '{query}' to visual text '{target}'.")
            return match

    print(f"[OCR-SEMANTIC] Could not map intent '{query}' to any visible text.")
    return None


def wait_for_text(label: str, page, timeout_ms: int = 5000, exact: bool = False, min_conf: float = 0.6) -> Optional[dict]:
    """
    Visually waits for a label to appear on screen.
    Replaces brittle sleeps with deterministic state polling.
    """
    start_time = time.monotonic()
    timeout_sec = timeout_ms / 1000.0
    temp_path = os.path.join(WORKSPACE_DIR, "logs", f"wait_{uuid.uuid4().hex[:8]}.png")
    os.makedirs(os.path.dirname(temp_path), exist_ok=True)

    try:
        while (time.monotonic() - start_time) < timeout_sec:
            try:
                page.screenshot(path=temp_path)
                match = find(label, temp_path, exact=exact, min_conf=min_conf, page=page)
                if match:
                    elapsed = int((time.monotonic() - start_time) * 1000)
                    print(f"[OCR-WAIT] Found '{label}' after {elapsed}ms.")
                    return match
            except Exception:
                # Transient navigation or detached execution context; wait and retry
                pass

            try:
                page.wait_for_timeout(200)
            except Exception:
                break
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass

    elapsed = int((time.monotonic() - start_time) * 1000)
    print(f"[OCR-WAIT] Timed out after {elapsed}ms looking for '{label}'.")
    return None
