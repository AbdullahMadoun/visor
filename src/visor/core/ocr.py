import cv2
import sys
from typing import Optional
import difflib

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
        import os
        langs = os.environ.get("EASYOCR_LANGS", "en").split(",")
        _reader = easyocr.Reader(langs, gpu=True)
        _use_ocrmac = False
    return _reader

def find_all(img_path: str) -> list:
    """
    Run OCR on image, return all found text with positions.
    Returns list of: {text, x, y, x1, y1, x2, y2, confidence}
    """
    reader = get_reader()
    items = []
    
    # Retina Scaling Fix: Get actual devicePixelRatio from browser
    from visor.core import browser
    try:
        page = browser.get_page()
        scale_factor = float(page.evaluate("window.devicePixelRatio"))
    except Exception:
        scale_factor = 2.0 if _use_ocrmac else 1.0

    if _use_ocrmac:
        # ocrmac returns: (text, confidence, [x, y, w, h]) where coordinates are ratios (0-1)
        # Note: Origin (0,0) in ocrmac bounding boxes is bottom-left!
        img = cv2.imread(img_path)
        if img is None: return []
        h_img, w_img, _ = img.shape
        
        results = reader.OCR(img_path).recognize()
        for text, conf, bbox in results:
            if conf < 0.1: continue # very low confidence
            # bbox is [x, y, w, h] as floats between 0 and 1
            bx, by, bw, bh = bbox
            x_min = int(bx * w_img)
            w_px = int(bw * w_img)
            h_px = int(bh * h_img)
            # ocrmac origin is bottom-left. Convert y to top-left origin.
            y_max = h_img - int(by * h_img)
            y_min = y_max - h_px
            
            cx = x_min + (w_px // 2)
            cy = y_min + (h_px // 2)
            
            # Apply scale factor to sync vision coordinates with Playwright CSS coordinates
            items.append({
                "text": text.strip(),
                "x": int(cx / scale_factor),
                "y": int(cy / scale_factor),
                "x1": int(x_min / scale_factor), "y1": int(y_min / scale_factor),
                "x2": int((x_min + w_px) / scale_factor), "y2": int(y_max / scale_factor),
                "confidence": round(conf, 3)
            })
    else:
        img = cv2.imread(img_path)
        if img is None: return []
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


def find(label: str, img_path: str, exact: bool = True,
         min_conf: float = 0.6,
         bounds: dict = None) -> Optional[dict]:
    """
    Find a label in the screenshot — geometrically smart.

    Strategy (in order):
    1. If bounds given: strictly filter OCR results to only those whose 
       center (cx, cy) falls within the provided bounds (x, y, w, h).
       This solves sidebar/feed ambiguity by mapping DOM logical containers 
       to visual OCR boundaries.
    2. Otherwise: return the LEFTMOST match among all matches

    Args:
        label:         Text to find
        img_path:      Screenshot path
        exact:         If True, exact match; if False, substring match
        min_conf:      Minimum OCR confidence
        bounds:        Optional dict {"x": int, "y": int, "w": int, "h": int}
    """
    all_items = find_all(img_path)

    def matches(item):
        text = item["text"].lower().strip()
        target = label.lower().strip()
        if item["confidence"] < min_conf:
            return False
            
        if exact:
            if text == target: return True
            return difflib.SequenceMatcher(None, text, target).ratio() >= 0.85
            
        if target in text: return True
        
        for w in text.split():
            if difflib.SequenceMatcher(None, w, target).ratio() >= 0.80:
                return True
        return difflib.SequenceMatcher(None, text, target).ratio() >= 0.80

    candidates = [item for item in all_items if matches(item)]
    
    # Strategy 1: bounds filtering
    if bounds:
        bx, by, bw, bh = bounds["x"], bounds["y"], bounds["w"], bounds["h"]
        candidates = [
            c for c in candidates
            if bx <= c["x"] <= bx + bw and by <= c["y"] <= by + bh
        ]
        if not candidates:
            print(f"[OCR] '{label}' not found within specified DOM bounds.")
            return None

    if not candidates:
        return None

    # Strategy 2: highest confidence match (most robust fallback)
    result = max(candidates, key=lambda c: c["confidence"])
    print(f"[OCR] Found '{label}' (highest conf: {result['confidence']}) at x={result['x']}, y={result['y']}")
    return result



def find_near(label: str, img_path: str, near_x: int, near_y: int,
              radius: int = 150, exact: bool = True, min_conf: float = 0.7) -> Optional[dict]:
    """
    Find label within a radius of a known (x, y) point.
    Useful for finding elements inside dropdowns that just opened near a button.
    """
    all_items = find_all(img_path)
    candidates = []
    def matches(item):
        text = item["text"].lower().strip()
        target = label.lower().strip()
        if item["confidence"] < min_conf:
            return False
            
        if exact:
            if text == target: return True
            return difflib.SequenceMatcher(None, text, target).ratio() >= 0.85
            
        if target in text: return True
        
        for w in text.split():
            if difflib.SequenceMatcher(None, w, target).ratio() >= 0.80:
                return True
        return difflib.SequenceMatcher(None, text, target).ratio() >= 0.80

    for item in all_items:
        if matches(item):
            dist = ((item["x"] - near_x) ** 2 + (item["y"] - near_y) ** 2) ** 0.5
            if dist <= radius:
                candidates.append((dist, item))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def summarize(img_path: str) -> list:
    """Return all found text strings for agent analysis."""
    return [item["text"] for item in find_all(img_path)]
