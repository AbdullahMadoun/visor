import os
import sys
import uuid
import time
import difflib
from typing import Optional
import cv2

from visor.core import WORKSPACE_DIR

_reader = None
_use_ocrmac = False

def get_reader():
    global _reader, _use_ocrmac
    if _reader is None:
        try:
            if sys.platform == 'darwin':
                from ocrmac import ocrmac
                print("[OCR] Successfully loaded native Apple Vision API (ocrmac). Lightning fast mode enabled.")
                _reader = ocrmac
                _use_ocrmac = True
                return _reader
        except ImportError:
            pass
            
        print("[OCR] ocrmac not found or incompatible. Falling back to EasyOCR (GPU/MPS)...")
        import easyocr
        langs = os.environ.get("EASYOCR_LANGS", "en").split(",")
        _reader = easyocr.Reader(langs, gpu=True)
        _use_ocrmac = False
    return _reader


def _resolve_scale_factor(img_w: int) -> float:
    """
    Safely resolves the scale factor without triggering an unintended browser launch.
    Derives scaling deterministically from screenshot width vs viewport CSS width.
    """
    from visor.core import browser
    if browser._page is not None:
        try:
            if not browser._page.is_closed():
                vp = browser._page.viewport_size
                if vp and vp.get("width"):
                    return max(1.0, round(img_w / float(vp["width"]), 2))
                return float(browser._page.evaluate("window.devicePixelRatio"))
        except Exception:
            pass
    return 1.0


def find_all(img_path: str) -> list:
    """
    Run OCR on image, return all found text with positions.
    Returns list of: {text, x, y, x1, y1, x2, y2, confidence}
    """
    reader = get_reader()
    items = []

    img = cv2.imread(img_path)
    if img is None:
        return []
    h_img, w_img, _ = img.shape

    scale_factor = _resolve_scale_factor(w_img)

    if _use_ocrmac:
        # ocrmac returns: (text, confidence, [x, y, w, h]) where coordinates are ratios (0-1)
        # Note: Origin (0,0) in ocrmac bounding boxes is bottom-left!
        results = reader.OCR(img_path).recognize()
        for text, conf, bbox in results:
            if conf < 0.1:
                continue
            bx, by, bw, bh = bbox
            x_min = int(bx * w_img)
            w_px = int(bw * w_img)
            h_px = int(bh * h_img)
            # ocrmac origin is bottom-left. Convert y to top-left origin.
            y_max = h_img - int(by * h_img)
            y_min = y_max - h_px
            
            cx = x_min + (w_px // 2)
            cy = y_min + (h_px // 2)
            
            items.append({
                "text": text.strip(),
                "x": int(cx / scale_factor),
                "y": int(cy / scale_factor),
                "x1": int(x_min / scale_factor), "y1": int(y_min / scale_factor),
                "x2": int((x_min + w_px) / scale_factor), "y2": int(y_max / scale_factor),
                "confidence": round(conf, 3)
            })
    else:
        results = reader.readtext(img)
        for (bbox, text, prob) in results:
            tl, tr, br, bl = bbox
            cx = int((tl[0] + br[0]) / 2)
            cy = int((tl[1] + br[1]) / 2)
            items.append({
                "text": text.strip(),
                "x": int(cx / scale_factor),
                "y": int(cy / scale_factor),
                "x1": int(tl[0] / scale_factor), "y1": int(tl[1] / scale_factor),
                "x2": int(br[0] / scale_factor), "y2": int(br[1] / scale_factor),
                "confidence": round(prob, 3)
            })
            
    return items


def _score_match(candidate_text: str, target: str, exact: bool) -> tuple[int, float]:
    """
    Hierarchical match scoring to prevent false positives and confidence inversion:
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
         bounds: dict = None) -> Optional[dict]:
    """
    Find a label in the screenshot — geometrically and hierarchically ranked.
    Exact matches outrank fuzzy matches regardless of OCR confidence score.
    """
    all_items = find_all(img_path)

    scored = []
    for item in all_items:
        if item["confidence"] < min_conf:
            continue
        tier, ratio = _score_match(item["text"], label, exact)
        if tier > 0:
            scored.append((tier, ratio, item["confidence"], item))

    # Apply DOM bounds constraint if specified
    if bounds:
        bx, by, bw, bh = bounds["x"], bounds["y"], bounds["w"], bounds["h"]
        scored = [
            s for s in scored
            if bx <= s[3]["x"] <= bx + bw and by <= s[3]["y"] <= by + bh
        ]
        if not scored:
            print(f"[OCR] '{label}' not found within specified DOM bounds.")
            return None

    if not scored:
        return None

    # Sort hierarchy: Tier DESC, Similarity Ratio DESC, OCR Confidence DESC
    scored.sort(key=lambda s: (s[0], s[1], s[2]), reverse=True)
    best = scored[0][3]
    print(f"[OCR] Found '{label}' (tier={scored[0][0]}, conf={best['confidence']}) at x={best['x']}, y={best['y']}")
    return best


def find_near(label: str, img_path: str, near_x: int, near_y: int,
              radius: int = 150, exact: bool = True, min_conf: float = 0.7) -> Optional[dict]:
    """
    Find label within a radius of a known (x, y) point (e.g. inside a newly opened dropdown).
    """
    all_items = find_all(img_path)
    candidates = []

    for item in all_items:
        if item["confidence"] < min_conf:
            continue
        tier, ratio = _score_match(item["text"], label, exact)
        if tier > 0:
            dist = ((item["x"] - near_x) ** 2 + (item["y"] - near_y) ** 2) ** 0.5
            if dist <= radius:
                candidates.append((tier, ratio, dist, item))

    if not candidates:
        return None

    # Prefer highest match tier, then shortest distance
    candidates.sort(key=lambda c: (-c[0], c[2]))
    return candidates[0][3]


def summarize(img_path: str) -> list:
    """Return all found text strings for agent analysis."""
    return [item["text"] for item in find_all(img_path)]


def find_with_scroll(label: str, page, max_scrolls: int = 5, exact: bool = False, min_conf: float = 0.6) -> Optional[dict]:
    """
    Auto-scroll discovery engine.
    Pages down and searches iteratively until the target is found.
    """
    for i in range(max_scrolls + 1):
        img_path = os.path.join(WORKSPACE_DIR, "logs", f"scroll_scan_{i}.png")
        page.screenshot(path=img_path)
        match = find(label, img_path, exact=exact, min_conf=min_conf)
        if match:
            print(f"[OCR-SCROLL] Found '{label}' after {i} scrolls at ({match['x']}, {match['y']}).")
            return match
            
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

def semantic_find(query: str, img_path: str, min_conf: float = 0.6, custom_dict: dict = None) -> Optional[dict]:
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
        is_exact = len(target) <= 4
        match = find(target, img_path, exact=is_exact, min_conf=min_conf)
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
                match = find(label, temp_path, exact=exact, min_conf=min_conf)
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
