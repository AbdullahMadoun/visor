"""
Actions — find things on screen by their visible text and act on them.

OCR finds the text. When a live page is available, visor then asks the browser
what sits under that pixel, to tell a real button from plain text, wait out
disabled buttons and notice overlays: the browser confirms what OCR saw, it
does not replace it. Only when OCR cannot see the text at all (icon-only
buttons, text inside images) does visor look the element up by accessible name.

Every action that needs to find text climbs the same ladder until one works:
  1. look, re-looking while the page is still changing (up to `timeout`)
  2. captcha / two-factor prompt on screen: HUMAN_HANDSHAKE, wait for you to solve it
  3. close a cookie banner or overlay that may hide it
  4. scroll the page to bring it into view
  5. look it up by accessible name (icon-only buttons)
  6. strategy tree / AGENT_HANDSHAKE (clicks inside run_flow only)
"""
import os
import time
from typing import Optional

from visor.config import settings
from visor.core import browser, clicker, ocr, WORKSPACE_DIR
from visor.errors import TextNotFound, ElementDisabled, NavigationError, VisorError, Skip, RestartFlow

# Effects that prove a click reached the page; focus/scroll changes alone are weaker evidence
_STRONG_EFFECTS = ("navigated", "changed the page", "sent a request", "opened a new tab", "closed the tab",
                   "started a download")


# ── Browser-side probes ──────────────────────────────────────────────────────

_SHARED_JS = """
  const CONTROL = 'a[href],button,input:not([type=hidden]),select,textarea,summary,label,option,' +
    '[role=button],[role=link],[role=menuitem],[role=menuitemradio],[role=menuitemcheckbox],[role=tab],' +
    '[role=option],[role=checkbox],[role=radio],[role=switch],[role=combobox],[role=textbox],[role=searchbox],' +
    '[onclick],[contenteditable=""],[contenteditable=true]';
  const FIELD = 'input:not([type=hidden]):not([type=button]):not([type=submit]):not([type=reset])' +
    ':not([type=checkbox]):not([type=radio]):not([type=file]):not([type=image]),textarea,select,' +
    '[contenteditable=""],[contenteditable=true],[role=textbox],[role=searchbox],[role=combobox]';
  const up = (n) => n.parentElement || (n.getRootNode && n.getRootNode().host) || null;
  const closest = (el, sel) => { for (let n = el; n; n = up(n)) if (n.matches && n.matches(sel)) return n; return null; };
  const topAt = (x, y) => {
    let el = document.elementFromPoint(x, y);
    while (el && el.shadowRoot) {
      const inner = el.shadowRoot.elementFromPoint(x, y);
      if (!inner || inner === el) break;
      el = inner;
    }
    return el;
  };
"""

# What sits under each OCR hit: a control? disabled? inside an overlay?
_PROBE_JS = "(points) => {" + _SHARED_JS + """
  const DIALOG = 'dialog[open],[role=dialog],[role=alertdialog],[aria-modal=true]';
  const layerOf = (el) => {
    for (let n = el; n && n !== document.body && n !== document.documentElement; n = up(n)) {
      if (!n.matches) continue;
      if (n.matches(DIALOG)) return [n, 'dialog'];
      const pos = getComputedStyle(n).position;
      if (pos === 'fixed' || pos === 'sticky') return [n, pos];
    }
    return [null, ''];
  };
  const names = (n) => [n.innerText, n.value, n.getAttribute('aria-label'), n.getAttribute('title'),
                        n.getAttribute('placeholder'), n.getAttribute('alt')].filter(Boolean).join(' ').slice(0, 400);
  // The form holding the field being typed in: its own button beats a same-named one elsewhere
  let focused = document.activeElement;
  while (focused && focused.shadowRoot && focused.shadowRoot.activeElement) focused = focused.shadowRoot.activeElement;
  const focusForm = focused && focused !== document.body && focused.matches && focused.matches(FIELD) ? closest(focused, 'form') : null;
  return points.map(([x, y]) => {
    const el = topAt(x, y);
    if (!el) return null;
    const control = closest(el, CONTROL);
    const node = control || el;
    const [layer, kind] = layerOf(el);
    return {
      tag: node.tagName.toLowerCase(),
      clickable: !!control || getComputedStyle(el).cursor === 'pointer',
      field: !!closest(el, FIELD),
      opaque: ['iframe', 'canvas', 'img', 'svg', 'video', 'embed', 'object'].includes(el.tagName.toLowerCase()),
      disabled: !!(control && (control.disabled || control.getAttribute('aria-disabled') === 'true' ||
                               (control.closest && control.closest('fieldset[disabled]')))),
      text: names(node),
      side: !!closest(node, 'aside,[role=complementary]'),
      inForm: !!(focusForm && closest(node, 'form') === focusForm),
      newTab: (() => { const a = closest(el, 'a[target],form[target]');
                       return !!a && !['', '_self', '_top', '_parent'].includes(a.getAttribute('target')); })(),
      layer: kind,
      layerText: layer ? (layer.innerText || '').slice(0, 600) : '',
    };
  });
}"""

# How closely each point is related to the anchor in the page: the depth of their deepest shared
# container (0 if unknown). A form's button shares the form with its heading; a sidebar link doesn't.
_KIN_JS = "([anchor, points]) => {" + _SHARED_JS + """
  const chain = (el) => { const out = []; for (let n = el; n; n = up(n)) out.push(n); return out; };
  const a = topAt(anchor[0], anchor[1]);
  if (!a) return points.map(() => 0);
  const mine = new Set(chain(a));
  return points.map(([x, y]) => {
    const el = topAt(x, y);
    const shared = el && chain(el).find((n) => mine.has(n));
    return shared ? chain(shared).length : 0;
  });
}"""

# Every control a person could click right now, by role and accessible name. Only controls that are
# on screen and painted on top at their centre (not covered), so the list matches what can be clicked.
_CONTROLS_JS = "(limit) => {" + _SHARED_JS + """
  const SEL = 'button,a[href],summary,select,textarea,input:not([type=hidden]),[role=button],[role=link],' +
              '[role=menuitem],[role=tab],[role=checkbox],[role=radio],[role=switch],[role=combobox],[role=option]';
  const roleOf = (el) => el.getAttribute('role') || ({A: 'link', SELECT: 'combobox', TEXTAREA: 'textbox',
      SUMMARY: 'button', BUTTON: 'button'}[el.tagName] ||
      (el.tagName === 'INPUT' ? ({checkbox: 'checkbox', radio: 'radio', submit: 'button', button: 'button',
                                  search: 'searchbox'}[el.type] || 'textbox') : el.tagName.toLowerCase()));
  const nameOf = (el) => {
    const by = el.getAttribute('aria-labelledby');
    const ref = by && by.split(/\\s+/).map((id) => document.getElementById(id)).filter(Boolean)
                        .map((n) => n.innerText).join(' ');
    const img = el.querySelector && el.querySelector('img[alt],svg[aria-label]');
    const lab = el.labels && el.labels[0] && el.labels[0].innerText;
    return (el.getAttribute('aria-label') || ref || lab || (el.innerText || '').trim() || el.getAttribute('title') ||
            (img && (img.getAttribute('alt') || img.getAttribute('aria-label'))) ||
            el.getAttribute('placeholder') || (el.type === 'submit' && el.value) || '').replace(/\\s+/g, ' ').trim();
  };
  const out = [], seen = new Set();
  for (const el of document.querySelectorAll(SEL)) {
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2 || r.bottom <= 0 || r.right <= 0 || r.top >= innerHeight || r.left >= innerWidth) continue;
    const x = Math.min(Math.max(r.left + r.width / 2, 0), innerWidth - 1), y = Math.min(Math.max(r.top + r.height / 2, 0), innerHeight - 1);
    const top = topAt(x, y);
    if (!top || !(top === el || el.contains(top) || top.control === el || (top.closest && top.closest('label') && top.closest('label').control === el))) continue;
    const name = nameOf(el).slice(0, 80);
    const key = roleOf(el) + '|' + name;
    if (!name || seen.has(key)) continue;
    seen.add(key);
    out.push({role: roleOf(el), name, x: Math.round(x), y: Math.round(y),
              disabled: !!(el.disabled || el.getAttribute('aria-disabled') === 'true')});
    if (out.length >= limit) break;
  }
  return out;
}"""

# The input a visible label belongs to: under it, its <label> control, or the nearest field below/right
_FIELD_JS = "([x1, y1, x2, y2]) => {" + _SHARED_JS + """
  const cx = (x1 + x2) / 2, cy = (y1 + y2) / 2;
  const onScreen = (r) => r.width > 2 && r.height > 2 && r.bottom > 0 && r.right > 0 && r.top < innerHeight && r.left < innerWidth;
  const centre = (el) => { const r = el.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2, el.tagName.toLowerCase()]; };
  const el = topAt(cx, cy);
  if (el) {
    const direct = closest(el, FIELD);
    if (direct) return centre(direct);
    const lab = closest(el, 'label');
    const ctl = lab && (lab.control || lab.querySelector(FIELD));
    if (ctl && onScreen(ctl.getBoundingClientRect())) return centre(ctl);
    const owner = closest(el, '[id]');
    if (owner) {
      const ref = document.querySelector('[aria-labelledby~="' + CSS.escape(owner.id) + '"]');
      if (ref && ref.matches(FIELD) && onScreen(ref.getBoundingClientRect())) return centre(ref);
    }
  }
  let best = null, bestScore = Infinity;
  for (const f of document.querySelectorAll(FIELD)) {
    const r = f.getBoundingClientRect();
    if (!onScreen(r) || f.disabled || f.readOnly) continue;
    const st = getComputedStyle(f);
    if (st.visibility === 'hidden' || st.display === 'none') continue;
    const dx = Math.max(r.left - x2, x1 - r.right, 0), dy = Math.max(r.top - y2, y1 - r.bottom, 0);
    let score = Math.hypot(dx, dy * 1.5);
    if (r.top >= y1 - 6 && r.left >= x1 - 60) score *= 0.5;  // below or to the right, the way forms are laid out
    if (score < bestScore) { bestScore = score; best = f; }
  }
  return best && bestScore < 220 ? centre(best) : null;
}"""

# Focus a <select> without clicking it (a click opens the native dropdown, which code can't close)
_FOCUS_AT_JS = "([x, y]) => {" + _SHARED_JS + """
  const el = closest(topAt(x, y), 'select');
  if (el) el.focus();
  return !!el;
}"""

# The checkbox / radio / switch a visible label belongs to, and whether it is on
_TOGGLE_JS = "([x1, y1, x2, y2]) => {" + _SHARED_JS + """
  const TOGGLE = 'input[type=checkbox],input[type=radio],[role=checkbox],[role=radio],[role=switch]';
  const state = (t) => t.matches('input') ? t.checked : t.getAttribute('aria-checked') === 'true';
  const describe = (t, viaLabel) => {
    const r = t.getBoundingClientRect();
    return {x: r.left + r.width / 2, y: r.top + r.height / 2, visible: r.width > 3 && r.height > 3,
            checked: state(t), viaLabel};
  };
  const el = topAt((x1 + x2) / 2, (y1 + y2) / 2);
  if (el) {
    const own = closest(el, TOGGLE);
    if (own) return describe(own, false);
    const lab = closest(el, 'label');
    const ctl = lab && (lab.control || lab.querySelector(TOGGLE));
    if (ctl && ctl.matches(TOGGLE)) return describe(ctl, true);
  }
  let best = null, bestScore = Infinity;
  for (const t of document.querySelectorAll(TOGGLE)) {
    const r = t.getBoundingClientRect();
    if (r.width < 3 || r.height < 3) continue;
    const dy = Math.abs((r.top + r.bottom) / 2 - (y1 + y2) / 2);
    const dx = r.right <= x1 ? x1 - r.right : (r.left >= x2 ? r.left - x2 : 0);
    if (dy > Math.max(14, (y2 - y1))) continue;  // same row only
    const score = dx + (r.left >= x2 ? 20 : 0);    // boxes usually sit left of their text
    if (score < bestScore) { bestScore = score; best = t; }
  }
  return best && bestScore < 120 ? describe(best, false) : null;
}"""

_FOCUS_JS = "() => {" + _SHARED_JS + """
  let a = document.activeElement;
  while (a && a.shadowRoot && a.shadowRoot.activeElement) a = a.shadowRoot.activeElement;
  if (!a || a === document.body) return {field: false, tag: '', value: ''};
  return {field: a.matches(FIELD) || a.isContentEditable, tag: a.tagName.toLowerCase(),
          value: a.isContentEditable ? a.innerText : (a.value == null ? '' : String(a.value))};
}"""

_ARM_JS = """() => {
  if (!window.__visorObserver) {
    window.__visorMutations = 0;
    window.__visorObserver = new MutationObserver((list) => { window.__visorMutations += list.length; });
    window.__visorObserver.observe(document, {subtree: true, childList: true, attributes: true, characterData: true});
  }
  window.__visorMutations = 0;
  const a = document.activeElement;
  return [location.href, a ? a.tagName + '#' + a.id + '.' + a.name : '', window.scrollX, window.scrollY];
}"""

_EFFECT_JS = """() => {
  const a = document.activeElement;
  return [location.href, window.__visorMutations || 0, a ? a.tagName + '#' + a.id + '.' + a.name : '',
          window.scrollX, window.scrollY];
}"""

_MODAL_JS = """() => [...document.querySelectorAll('dialog[open],[role=dialog],[role=alertdialog],[aria-modal=true]')]
  .some((d) => { const r = d.getBoundingClientRect(); return r.width > 10 && r.height > 10 && getComputedStyle(d).visibility !== 'hidden'; })"""


def _probe(points: list) -> list:
    """Ask the page what sits under each (x, y). None entries when the page can't answer."""
    if not points:
        return []
    try:
        return browser.get_page().evaluate(_PROBE_JS, [[float(x), float(y)] for x, y in points])
    except Exception:
        return [None] * len(points)


def _kin(anchor, points: list) -> list:
    try:
        return browser.get_page().evaluate(_KIN_JS, [[float(anchor[0]), float(anchor[1])],
                                                     [[float(x), float(y)] for x, y in points]])
    except Exception:
        return [0] * len(points)


def _contains(text: str, label: str) -> bool:
    want = ocr.normalize(label).replace(" ", "")
    return bool(want) and want in ocr.normalize(text).replace(" ", "")


def _is_covered(info: Optional[dict], label: str) -> bool:
    """OCR sees the label here, but the element on top is an overlay that doesn't contain it."""
    return bool(info and info.get("layer") and not info.get("field")
                and not _contains(info.get("text", ""), label)
                and not _contains(info.get("layerText", ""), label))


# ── Choosing what to act on ──────────────────────────────────────────────────

def _labels(label) -> list:
    labels = [str(x) for x in label] if isinstance(label, (list, tuple)) else [str(label)]
    labels = [x for x in labels if x.strip()]
    if not labels:
        raise ValueError(f"Nothing to look for: {label!r}")
    return labels


def _control_score(m: dict) -> int:
    info = m.get("info")
    if not info:
        return 1  # the page couldn't tell; neutral
    if info.get("clickable") or info.get("field"):
        return 2
    return 1 if info.get("opaque") else 0


def _rank(m: dict) -> tuple:
    # Word-for-word matches first; among those prefer real controls, enabled, uncovered; then OCR's own ranking.
    info = m.get("info") or {}
    # Ties: the form you are typing in beats the rest of the page, and a sidebar (<aside>) loses.
    return (m["tier"] >= 3, _control_score(m), not info.get("disabled"), not m.get("covered"),
            bool(info.get("inForm")), not info.get("side"), m["tier"], m["ratio"], m["confidence"], -m["order"], -m["start"])


def _choose(matches: list, near=None, index: int = None) -> Optional[dict]:
    ranked = sorted(matches, key=_rank, reverse=True)
    top = ranked[0]
    same = [m for m in ranked if _rank(m)[:2] == _rank(top)[:2] and m["tier"] == top["tier"]]
    if near is not None:
        nx, ny = near
        # The one sharing the deepest container with the anchor wins (same form, card or row);
        # then distance, with same-row neighbours closer in meaning than same-column ones
        kin = _kin(near, [(m["x"], m["y"]) for m in same]) if len(same) > 1 else [0]
        return min(zip(kin, same), key=lambda km: (-km[0], (km[1]["x"] - nx) ** 2
                                                   + (2 * (km[1]["y"] - ny)) ** 2))[1]
    if index is not None:
        ordered = sorted(same, key=lambda m: (m["order"], m["start"]))
        return ordered[index] if -len(ordered) <= index < len(ordered) else None
    return top


def _scan(labels: list, near=None, index: int = None, exact: bool = False, region=None,
          probe: bool = True, img_path: str = None, proof: bool = False) -> tuple:
    """
    One look at the screen. Returns (best match or None, list of visible texts).
    proof=True: only whole-word matches count, for checking a result rather than aiming a click.
    """
    img = img_path or look()
    page = browser.get_page()
    items = ocr.find_all(img, page)
    visible = [item["text"] for item in items]

    anchor = near
    if isinstance(near, str):
        anchors = ocr.find_matches(near, exact=False, min_conf=settings.min_conf, items=items)
        if not anchors:
            return None, visible
        anchor = (anchors[0]["x"], anchors[0]["y"])

    for label in labels:  # alternatives, in order of preference
        matches = ocr.find_matches(label, exact=exact, min_conf=settings.min_conf, items=items)
        if region:
            matches = [m for m in matches if ocr._in_bounds(m, region)]
        if proof:
            matches = [m for m in matches if m["tier"] >= ocr.PROOF_TIER]
        if not matches:
            continue
        matches = matches[:12]
        if probe:
            for m, info in zip(matches, _probe([(m["x"], m["y"]) for m in matches])):
                m["info"] = info
                m["covered"] = _is_covered(info, label)
        chosen = _choose(matches, anchor, index)
        if chosen:
            chosen["label"] = label
            chosen["disabled"] = bool((chosen.get("info") or {}).get("disabled"))
            return chosen, visible
    return None, visible


def _poll(labels: list, seconds: float, probe: bool = True, **scan) -> tuple:
    """Re-look until a usable match shows up or `seconds` pass. Returns (match, visible)."""
    deadline = time.monotonic() + seconds
    while True:
        found, visible = _scan(labels, probe=probe, **scan)
        if found and not found["disabled"]:
            return found, visible
        if time.monotonic() >= deadline:
            return found, visible
        browser.wait(300)


def _acquire(label, *, near=None, index=None, exact=False, timeout=None, scroll=None,
             region=None, heal=False, purpose="click") -> dict:
    """Climb the ladder until the label is found and usable; raise TextNotFound otherwise."""
    labels = _labels(label)
    timeout = settings.timeout if timeout is None else timeout
    scan = dict(near=near, index=index, exact=exact, region=region)
    start = time.monotonic()

    # 1. Look; keep looking while the page is still changing
    previous, unchanged = None, 0
    while True:
        found, visible = _scan(labels, **scan)
        if found and not found["disabled"]:
            return found
        unchanged = unchanged + 1 if visible == previous else 0
        previous = visible
        elapsed = time.monotonic() - start
        if elapsed >= timeout:
            break
        # A static screen won't grow the text by waiting longer; disabled buttons get the full timeout
        if not found and unchanged >= 2 and elapsed >= 1.5:
            break
        browser.wait(300)
    if found and found["disabled"]:
        raise ElementDisabled(f"{found['label']!r} is on screen but stayed disabled for {timeout:.0f}s")

    # 2. A captcha or 2FA prompt is in the way: hand over to the human, then look again
    if settings.human and blocker(visible):
        human_handshake(f"{blocker(visible)!r} is on screen while looking for {labels[0]!r}")
        found, visible = _poll(labels, timeout, **scan)
        if found and not found["disabled"]:
            return found

    # 3. A cookie banner or overlay may be hiding it
    if settings.auto_dismiss and dismiss_popups():
        found, visible = _poll(labels, 2.0, **scan)
        if found and not found["disabled"]:
            return found

    # 4. Off screen: scroll it into view
    if settings.scroll_search if scroll is None else scroll:
        found = _scroll_search(labels, visible, **scan)
        if found:
            if found["disabled"]:
                found, _ = _poll([found["label"]], timeout, **scan)
                if not found or found["disabled"]:
                    raise ElementDisabled(f"{labels[0]!r} is on screen but stayed disabled")
            return found

    # 5. No visible text (icon-only button, text in an image): accessible name
    if settings.dom_fallback and near is None and index is None and region is None:
        found = _dom_locate(labels, purpose)
        if found:
            return found

    # 6. Self-healing: strategy tree, then the agent handshake
    if heal:
        from visor.core import runner
        status = runner.recover(labels[0], flow_key=settings.flow or "default")
        if status in ("success", "agent_fixed"):
            return {"label": labels[0], "healed": status, "effect": status}
        if status.startswith("skipped"):
            raise Skip(status.partition(":")[2] or "skipped")
        if status == "restart_flow":
            raise RestartFlow(labels[0])

    error = TextNotFound(" / ".join(labels), visible)
    if isinstance(near, str):
        error.args = (f"{error} (looked near {near!r})",)
    raise error


def _scroll_search(labels: list, visible_now: list, **scan) -> Optional[dict]:
    """Scroll down to the end, then up from the starting point, looking after each step."""
    page = browser.get_page()
    step = int(browser.viewport_size(page)["height"] * 0.75)
    try:
        origin = page.evaluate("[window.scrollX, window.scrollY]")
    except Exception:
        origin = None
    for direction in (1, -1):
        if direction == -1:
            if origin is None or origin[1] <= 0:
                break  # started at the top: nothing above
            page.evaluate("([x, y]) => window.scrollTo(x, y)", origin)
            browser.wait(300)
        previous = visible_now
        for _ in range(settings.max_scrolls):
            browser.scroll(direction * step, wait_ms=450)
            found, visible = _scan(labels, **scan)
            if found:
                print(f"[SCROLL] Found '{found['label']}' after scrolling {'down' if direction > 0 else 'up'}.")
                return found
            if visible == previous:  # the page stopped moving: reached the end
                break
            previous = visible
    if origin is not None:
        try:
            page.evaluate("([x, y]) => window.scrollTo(x, y)", origin)
        except Exception:
            pass
    return None


_HIT_JS = """(el, [x, y]) => {
    const top = document.elementFromPoint(x, y);
    return !!top && (top === el || el.contains(top) || (top.control && top.control === el));
}"""


def _dom_locate(labels: list, purpose: str) -> Optional[dict]:
    """Find an element by accessible name (aria-label, title, alt, label) when OCR sees no text."""
    page = browser.get_page()
    if purpose == "field":
        builders = [page.get_by_label, page.get_by_placeholder]
    else:
        builders = [lambda n, exact: page.get_by_role("button", name=n, exact=exact),
                    lambda n, exact: page.get_by_role("link", name=n, exact=exact),
                    lambda n, exact: page.get_by_role("menuitem", name=n, exact=exact),
                    lambda n, exact: page.get_by_role("tab", name=n, exact=exact),
                    page.get_by_title, page.get_by_alt_text, page.get_by_label]
    for label in labels:
        for exact_name in (True, False):
            for build in builders:
                try:
                    loc = build(label, exact=exact_name).locator("visible=true")
                    found = None
                    for k in range(min(loc.count(), 5)):
                        el = loc.nth(k)
                        el.scroll_into_view_if_needed(timeout=2000)
                        box = el.bounding_box()
                        if not box or box["width"] < 1 or box["height"] < 1:
                            continue
                        x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
                        # The click lands on whatever is painted at (x, y): it must be this element.
                        # (On LinkedIn a hidden "View profile" link sat under the menu's "Language".)
                        if el.evaluate(_HIT_JS, [x, y]):
                            found = el
                            break
                        print(f"[DOM] {label!r} by accessible name is covered at ({x:.0f}, {y:.0f}); not clicking it")
                    if found is None:
                        continue
                    el = found
                    print(f"[DOM] Found {label!r} by accessible name at ({x:.0f}, {y:.0f}) — no visible text")
                    return {"text": label, "label": label, "x": int(x), "y": int(y),
                            "x1": int(box["x"]), "y1": int(box["y"]),
                            "x2": int(box["x"] + box["width"]), "y2": int(box["y"] + box["height"]),
                            "confidence": 1.0, "tier": 0, "ratio": 0.0, "order": 0, "start": 0,
                            "source": "dom", "disabled": el.is_disabled(timeout=1000), "covered": False}
                except Exception:
                    continue
    return None


# ── Pressing ─────────────────────────────────────────────────────────────────

def _is_page_load(request, page) -> bool:
    try:
        return request.is_navigation_request() and request.frame == page.main_frame
    except Exception:
        return False


def _watch_effect(page, before, seen: dict, popups: int, window: float = 1.2) -> str:
    """Report what a click changed, waiting up to `window` seconds. '' means nothing visible happened."""
    deadline = time.monotonic() + window
    browser.wait(120)
    while True:
        if browser.popup_count() > popups:
            return "opened a new tab"
        if page.is_closed():
            return "closed the tab"
        if seen["download"]:
            return "started a download"
        if seen["nav"]:
            return "navigated"
        if any(_is_page_load(r, page) for r in seen["request"]):
            return "navigating"  # the request for the next page is out; it hasn't arrived yet
        if seen["request"]:
            return "sent a request"
        try:
            after = page.evaluate(_EFFECT_JS)
        except Exception:
            return "navigated"  # the document was replaced mid-check
        if before is None:
            return "unknown"
        if after[0] != before[0]:
            return "navigated"
        if after[1] > 0:
            return "changed the page"
        if after[2] != before[1]:
            return "moved focus"
        if (after[3], after[4]) != (before[2], before[3]):
            return "scrolled"
        if time.monotonic() >= deadline:
            return ""
        browser.wait(150)


def press(target: dict, double: bool = False) -> str:
    """Click a located target (from find/locate) and return what changed ('' if nothing did)."""
    page = browser.get_page()
    x, y = target["x"], target["y"]
    clicker.move(x, y)
    popups = browser.popup_count()
    seen = {"request": [], "nav": [], "download": []}

    # Plain functions: Playwright can't attach its wrapper to a bound list.append
    def on_request(request):
        seen["request"].append(request)

    def on_navigated(frame):
        if frame == page.main_frame:
            seen["nav"].append(frame.url)

    def on_download(download):
        seen["download"].append(download)

    listeners = (("request", on_request), ("framenavigated", on_navigated), ("download", on_download))
    try:
        before = page.evaluate(_ARM_JS)  # armed after the hover, so hover effects don't count
    except Exception:
        before = None
    for event, handler in listeners:
        page.on(event, handler)
    try:
        clicker.press_at(x, y, clicks=2 if double else 1)
        effect = _watch_effect(page, before, seen, popups)
        if effect == "navigating":
            # Wait for the new document (or a download) so the next look doesn't see the old page
            deadline = time.monotonic() + min(settings.nav_timeout, 15.0)
            while not (seen["nav"] or seen["download"]) and not page.is_closed() and time.monotonic() < deadline:
                browser.wait(100)
            effect = "started a download" if seen["download"] else "navigated"
    finally:
        for event, handler in listeners:
            try:
                page.remove_listener(event, handler)
            except Exception:
                pass
    # A link that says it opens a new tab may take a while to, on a slow machine: wait for it
    wait_ms = 3000 if (target.get("info") or {}).get("newTab") else (0 if effect else 300)
    if settings.follow_tabs and browser.follow_popup(popups, timeout_ms=wait_ms):
        effect = "opened a new tab"
    return effect


def _uncover(target: dict, **scan) -> dict:
    """Something sits on top of the target: try Escape, then closing popups, then look again."""
    label = target["label"]
    print(f"[CLICK] '{label}' is covered by an overlay. Pressing Escape...")
    clicker.press("Escape")
    browser.wait(300)
    found, _ = _scan([label], **scan)
    if found and not found.get("covered"):
        return found
    if settings.auto_dismiss and dismiss_popups():
        found, _ = _scan([label], **scan)
        if found and not found.get("covered"):
            return found
    print(f"[CLICK] '{label}' still looks covered; clicking anyway.")
    return found or target


# ── Public actions ───────────────────────────────────────────────────────────

def look() -> str:
    """Screenshot the active tab; returns the image path."""
    return browser.screenshot()


def goto(url: str) -> str:
    """Open a URL in the active tab and wait for it to settle. Returns the final URL."""
    try:
        browser.navigate(url)
    except Exception as e:
        raise NavigationError(f"Could not load {url}: {e}") from e
    return browser.get_page().url


def controls(limit: int = 60, visible_text: list = None) -> list:
    """
    The clickable controls on screen, by role and accessible name, for an agent deciding a fix.
    With visible_text (OCR's strings), each control notes whether its name can be read on screen:
    the ones that can't are icon-only, and only reachable by name.
    """
    try:
        found = browser.get_page().evaluate(_CONTROLS_JS, limit)
    except Exception:
        return []
    if visible_text is not None:
        seen = ocr.normalize(" ".join(visible_text)).replace(" ", "")
        for c in found:
            c["on_screen_text"] = ocr.normalize(c["name"]).replace(" ", "") in seen
    return found


def locate_target(label, **kw) -> Optional[dict]:
    """A fix's target: by visible text first, then by accessible name (it may come from failure.json's controls)."""
    found = locate(label, **kw)
    if found is None and settings.dom_fallback:
        found = _dom_locate(_labels(label), "click")
    return found


def locate(label, *, exact: bool = False, near=None, index: int = None, region=None,
           img_path: str = None) -> Optional[dict]:
    """The best on-screen match right now (no waiting), preferring real, enabled controls."""
    found, _ = _scan(_labels(label), near=near, index=index, exact=exact, region=region, img_path=img_path)
    return found


def find(label, *, timeout: float = 0, near=None, index: int = None, exact: bool = False,
         region=None) -> Optional[dict]:
    """Find text on screen, waiting up to `timeout` seconds. Returns the match dict or None."""
    found, _ = _poll(_labels(label), timeout, near=near, index=index, exact=exact, region=region)
    return found


def find_all(label, *, exact: bool = False, region=None) -> list:
    """Every place `label` is visible right now, in reading order."""
    matches = ocr.find_matches(label, look(), exact=exact, min_conf=settings.min_conf, page=browser.get_page())
    if region:
        matches = [m for m in matches if ocr._in_bounds(m, region)]
    best = matches[0]["tier"] if matches else 0
    return sorted([m for m in matches if m["tier"] == best], key=lambda m: (m["order"], m["start"]))


def see(label, *, exact: bool = False, region=None, proof: bool = False) -> bool:
    """Is the text visible right now? (No waiting, no scrolling.) proof=True: whole words only."""
    found, _ = _scan(_labels(label), exact=exact, region=region, probe=False, proof=proof)
    return found is not None


def click(label, *, near=None, index: int = None, exact: bool = False, timeout: float = None,
          scroll: bool = None, expect=None, double: bool = False, region=None, heal: bool = None) -> dict:
    """
    Click the button, link or text showing `label`.

    label:   the visible text, or a list of alternatives in order of preference
    near:    anchor text (or (x, y)) — pick the match closest to it, e.g. near="Blue mug"
    index:   pick the index-th equally good match in reading order (0 = first)
    expect:  text that should appear after the click; the click is retried once if it doesn't
    region:  (x1, y1, x2, y2) or {x, y, width, height} to search inside
    """
    heal = settings.heal if heal is None else heal
    target = _acquire(label, near=near, index=index, exact=exact, timeout=timeout,
                      scroll=scroll, region=region, heal=heal, purpose="click")
    if target.get("healed"):
        return target
    scan = dict(near=near, index=index, exact=exact, region=region)
    if target.get("covered"):
        target = _uncover(target, **scan)

    effect = press(target, double=double)
    if not effect and settings.verify_clicks:
        # Nothing reacted: the page may not have been ready, or the target moved. Look again, retry once.
        again, _ = _scan([target["label"]], **scan)
        if again is None:
            effect = "target disappeared"
        elif not again["disabled"]:
            print(f"[CLICK] '{target['label']}' showed no reaction; clicking once more...")
            target, effect = again, press(again, double=double)

    if expect is not None:
        if not _expect(expect, timeout):
            if effect in _STRONG_EFFECTS:
                raise TextNotFound(expect, read(), message=f"Clicked {target['label']!r} ({effect}) "
                                   f"but {expect!r} did not appear")
            print(f"[CLICK] {expect!r} did not appear; clicking '{target['label']}' again...")
            again, _ = _scan([target["label"]], **scan)
            if again:
                target, effect = again, press(again, double=double)
            wait_for(expect, timeout=timeout)

    target["effect"] = effect or "no visible change"
    print(f"[CLICK] '{target['label']}' -> {target['effect']}")
    if effect in ("navigated", "opened a new tab"):
        browser.settle(timeout=6.0)  # so the next look sees the new page, not a half-loaded one
    return target


def double_click(label, **kwargs) -> dict:
    return click(label, double=True, **kwargs)


def hover(label, *, near=None, index: int = None, exact: bool = False, timeout: float = None,
          region=None) -> dict:
    """Move the mouse over the text (opens hover menus and tooltips)."""
    target = _acquire(label, near=near, index=index, exact=exact, timeout=timeout, region=region)
    clicker.hover(target["x"], target["y"])
    browser.wait(400)
    return target


def fill(label, value: str, *, near=None, index: int = None, exact: bool = False, timeout: float = None,
         clear: bool = True, enter: bool = False) -> dict:
    """
    Type `value` into the field named by its visible label or placeholder
    (e.g. fill("Email", "me@example.com")). Native <select> boxes get the option with that text.
    """
    target = _acquire(label, near=near, index=index, exact=exact, timeout=timeout, purpose="field")
    page = browser.get_page()
    spot = None
    if target.get("source") != "dom" and not (target.get("info") or {}).get("field"):
        try:
            spot = page.evaluate(_FIELD_JS, [target["x1"], target["y1"], target["x2"], target["y2"]])
        except Exception:
            spot = None
    x, y = (int(spot[0]), int(spot[1])) if spot else (target["x"], target["y"])
    tag = spot[2] if spot else (target.get("info") or {}).get("tag", "")
    if not (tag == "select" and page.evaluate(_FOCUS_AT_JS, [x, y])):
        clicker.move(x, y)
        clicker.press_at(x, y)
        browser.wait(150)

    focus = page.evaluate(_FOCUS_JS)
    if focus["tag"] == "iframe":
        print(f"[FILL] '{target['label']}' is inside a frame; typing without verification")
    elif not focus["field"]:
        raise VisorError(f"Clicked {target['label']!r} but no text field took focus")

    if focus["tag"] == "select":
        field = page.locator(":focus")
        try:
            field.select_option(label=value, timeout=2000)
        except Exception:
            field.select_option(value=value, timeout=2000)
        print(f"[FILL] Selected {value!r} in '{target['label']}'")
    else:
        if clear:
            clicker.select_all()
            if not value:
                clicker.press("Backspace")
        if value:
            clicker.type_text(value)
        if focus["tag"] != "iframe" and value:
            typed = ocr.normalize(value).replace(" ", "")
            shown = page.evaluate(_FOCUS_JS)["value"]
            if typed and typed not in ocr.normalize(shown).replace(" ", ""):
                print(f"[FILL] Warning: field shows {shown!r} after typing {value!r}")
    if enter:
        clicker.press("Enter")
        browser.settle(timeout=4.0)
    target["field_at"] = (x, y)
    return target


def type_text(text: str, enter: bool = False):
    """Type into whatever has focus."""
    clicker.type_text(text)
    if enter:
        clicker.press("Enter")


def press_key(key: str):
    """Press a key or chord: "Enter", "Escape", "Tab", "Control+A"."""
    clicker.press(key)


def check(label, on: bool = True, *, near=None, index: int = None, timeout: float = None) -> dict:
    """
    Tick (on=True) or untick a checkbox, radio or switch by its visible label.
    Reads the current state first, so calling it twice never flips it back.
    """
    target = _acquire(label, near=near, index=index, timeout=timeout)
    page = browser.get_page()
    box = [target["x1"], target["y1"], target["x2"], target["y2"]]
    toggle = page.evaluate(_TOGGLE_JS, box) if target.get("source") != "dom" else None
    if toggle is None:
        raise VisorError(f"No checkbox, radio or switch found for {target['label']!r}")
    if toggle["checked"] == on:
        print(f"[CHECK] '{target['label']}' already {'on' if on else 'off'}")
        return target
    # Styled toggles often hide the real input: click the label text when it is linked, else the box
    spot = (target["x"], target["y"]) if toggle["viaLabel"] or not toggle["visible"] else (toggle["x"], toggle["y"])
    press(dict(target, x=int(spot[0]), y=int(spot[1])))
    toggle = page.evaluate(_TOGGLE_JS, box)
    if toggle and toggle["checked"] != on and toggle["visible"]:
        press(dict(target, x=int(toggle["x"]), y=int(toggle["y"])))  # the label wasn't wired up: hit the box itself
        toggle = page.evaluate(_TOGGLE_JS, box)
    if not toggle or toggle["checked"] != on:
        raise VisorError(f"Could not turn {target['label']!r} {'on' if on else 'off'}")
    print(f"[CHECK] '{target['label']}' -> {'on' if on else 'off'}")
    return target


def select(label, option: str, *, near=None, index: int = None, timeout: float = None) -> dict:
    """
    Choose `option` in the dropdown named `label`: native <select> boxes are set directly,
    custom dropdowns are opened and the option clicked (the one closest to the dropdown).
    """
    target = _acquire(label, near=near, index=index, timeout=timeout, purpose="field")
    page = browser.get_page()
    spot = None
    if target.get("source") != "dom":
        try:
            spot = page.evaluate(_FIELD_JS, [target["x1"], target["y1"], target["x2"], target["y2"]])
        except Exception:
            spot = None
    if spot and spot[2] == "select" and page.evaluate(_FOCUS_AT_JS, [spot[0], spot[1]]):
        field = page.locator(":focus")
        try:
            field.select_option(label=option, timeout=2000)
        except Exception:
            field.select_option(value=option, timeout=2000)
        print(f"[SELECT] {option!r} in '{target['label']}'")
        return target
    opener = dict(target, x=int(spot[0]), y=int(spot[1])) if spot else target
    press(opener)
    browser.wait(300)
    return click(option, near=(opener["x"], opener["y"]), timeout=timeout)


def upload(label, files, *, near=None, index: int = None, timeout: float = None) -> dict:
    """Click the upload button/area showing `label` and hand the file chooser `files` (a path or list)."""
    target = _acquire(label, near=near, index=index, timeout=timeout)
    page = browser.get_page()
    try:
        with page.expect_file_chooser(timeout=5000) as chooser:
            press(target)
        chooser.value.set_files(files)
    except Exception:
        # Some upload widgets don't open a chooser on click; fall back to the page's only file input
        inputs = page.locator("input[type=file]")
        if inputs.count() != 1:
            raise VisorError(f"Clicking {target['label']!r} did not open a file chooser")
        inputs.set_input_files(files)
    print(f"[UPLOAD] {files!r} via '{target['label']}'")
    return target


def download(label, save_to: str = None, *, near=None, index: int = None, timeout: float = None) -> str:
    """Click the link/button showing `label`, wait for the download, save it; returns the file path."""
    target = _acquire(label, near=near, index=index, timeout=timeout)
    page = browser.get_page()
    with page.expect_download(timeout=int(settings.nav_timeout * 1000)) as event:
        press(target)
    dl = event.value
    path = save_to or os.path.join(WORKSPACE_DIR, "downloads", dl.suggested_filename)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    dl.save_as(path)
    print(f"[DOWNLOAD] '{target['label']}' -> {path}")
    return path


def _expect(label, timeout: float = None) -> Optional[dict]:
    found, _ = _poll(_labels(label), settings.timeout if timeout is None else timeout, probe=False, proof=True)
    return found


def wait(seconds: float):
    """Pause for `seconds` (keeps the browser responsive while waiting)."""
    browser.wait(int(seconds * 1000))


def wait_for(label, *, timeout: float = None, exact: bool = False, region=None, proof: bool = False) -> dict:
    """Wait until the text is visible; returns the match or raises TextNotFound. proof=True: whole words only."""
    labels = _labels(label)
    found, visible = _poll(labels, settings.timeout if timeout is None else timeout,
                           probe=False, exact=exact, region=region, proof=proof)
    if found is None:
        raise TextNotFound(" / ".join(labels), visible)
    return found


def wait_gone(label, *, timeout: float = None, exact: bool = False) -> bool:
    """Wait until the text is no longer visible (spinners, 'Loading…', toasts)."""
    labels = _labels(label)
    deadline = time.monotonic() + (settings.timeout if timeout is None else timeout)
    while True:
        found, _ = _scan(labels, exact=exact, probe=False)
        if found is None:
            return True
        if time.monotonic() >= deadline:
            raise VisorError(f"{found['label']!r} was still visible after waiting")
        browser.wait(300)


def scroll_to(label, *, exact: bool = False, region=None) -> dict:
    """Scroll until the text is visible; returns the match or raises TextNotFound."""
    labels = _labels(label)
    found, visible = _scan(labels, exact=exact, region=region, probe=False)
    if found:
        return found
    found = _scroll_search(labels, visible, exact=exact, region=region, probe=False)
    if found is None:
        raise TextNotFound(" / ".join(labels), visible)
    return found


def scroll(direction="down", amount: int = None):
    """scroll("down"), scroll("up"), or scroll(600) / scroll(-600) pixels."""
    if isinstance(direction, (int, float)):
        dy = int(direction)
    else:
        step = amount or int(browser.viewport_size()["height"] * 0.75)
        dy = step if str(direction).lower() == "down" else -step
    browser.scroll(dy)


def read() -> list:
    """The visible text as lines, top to bottom."""
    return ocr.lines(look(), browser.get_page())


def text() -> str:
    """The visible text as one string."""
    return "\n".join(read())


# ── Popups ───────────────────────────────────────────────────────────────────

# Closing an overlay is the goal, not consenting: privacy-friendly choices are tried first.
DISMISS_LABELS = [
    "Reject all", "Reject all cookies", "Decline all", "Decline", "Only necessary", "Necessary only",
    "Use necessary cookies only", "Allow necessary only", "Continue without accepting",
    "No thanks", "No, thanks", "Not now", "Maybe later", "Dismiss", "Close", "Got it",
]
# Only clicked on banners that talk about cookies / consent / privacy
CONSENT_LABELS = ["Accept all", "Accept all cookies", "Accept cookies", "Allow all", "Allow all cookies",
                  "Accept", "I accept", "I agree", "Agree", "OK"]
CONSENT_WORDS = ("cookie", "consent", "privacy", "gdpr", "tracking", "personalis", "personaliz",
                 "ملفات تعريف الارتباط", "الخصوصية")


def dismiss_popups() -> bool:
    """Close a cookie banner, modal or overlay if one is showing. Returns True if something closed."""
    page = browser.get_page()
    items = ocr.find_all(look(), page)
    candidates = []
    for rank, label in enumerate(DISMISS_LABELS + CONSENT_LABELS):
        for m in ocr.find_matches(label, exact=True, min_conf=settings.min_conf, items=items)[:3]:
            if m["tier"] >= 4:  # the whole button text or a short phrase, never words in body text
                m["label"], m["rank"] = label, rank
                candidates.append(m)
    for m, info in sorted(zip(candidates, _probe([(m["x"], m["y"]) for m in candidates])),
                          key=lambda pair: pair[0]["rank"]):
        if not info or not info["clickable"] or not info["layer"]:
            continue  # only buttons living in an overlay (fixed bar, dialog)
        if m["label"] in CONSENT_LABELS and not any(w in info["layerText"].lower() for w in CONSENT_WORDS):
            continue
        print(f"[POPUP] Closing overlay via '{m['text']}'")
        press(m)
        browser.wait(300)
        return True

    # No labelled button: a modal with an icon-only close button, or one that closes on Escape
    try:
        if not page.evaluate(_MODAL_JS):
            return False
        close_btn = page.locator(
            ':is(dialog[open], [role=dialog], [role=alertdialog], [aria-modal=true]) '
            ':is([aria-label*="close" i], [aria-label*="dismiss" i], [title*="close" i])').locator("visible=true")
        if close_btn.count():
            box = close_btn.first.bounding_box()
            if box:
                print("[POPUP] Closing modal via its close button")
                press({"x": int(box["x"] + box["width"] / 2), "y": int(box["y"] + box["height"] / 2)})
                browser.wait(300)
                return True
        clicker.press("Escape")
        browser.wait(300)
        if not page.evaluate(_MODAL_JS):
            print("[POPUP] Closed modal with Escape")
            return True
    except Exception:
        pass
    return False


# ── Human handshake ──────────────────────────────────────────────────────────

# Walls only a person should get past
BLOCKER_PHRASES = (
    "captcha", "i'm not a robot", "im not a robot", "verify you are human", "verify you're human",
    "are you a robot", "security check", "unusual activity", "two-factor", "two-step verification",
    "2-step verification", "verification code", "enter the code", "one-time code", "one-time password",
)


def blocker(visible: list = None) -> Optional[str]:
    """The captcha / two-factor phrase on screen, if any."""
    screen = ocr.normalize(" ".join(read() if visible is None else visible))
    for phrase in BLOCKER_PHRASES:
        if ocr.normalize(phrase) in screen:
            return phrase
    return None


def human_handshake(reason: str = "needs a person", until=None, timeout: float = None) -> bool:
    """
    HUMAN_HANDSHAKE: pause so you can solve something in the browser yourself (captcha, 2FA, a login),
    then continue where the flow left off. Resumes when `until` text appears, when the captcha/2FA
    prompt is gone, or when you create agent_handshake/human_done. Raises VisorError on timeout.
    """
    if browser._owns_browser and settings.headless:
        raise VisorError(f"HUMAN_NEEDED but the browser is headless ({reason}). "
                         "Run without --headless (or attach to your Chrome) to solve it.")
    folder = os.path.join(WORKSPACE_DIR, "agent_handshake")
    os.makedirs(folder, exist_ok=True)
    done_flag = os.path.join(folder, "human_done")
    if os.path.exists(done_flag):
        os.remove(done_flag)
    print(f"\n{'='*60}\n[HUMAN_NEEDED] {reason}\n  Solve it in the browser window; visor continues by itself.\n"
          f"  (Or create {done_flag} to continue.)\n{'='*60}\n")
    try:
        browser.get_page().bring_to_front()
    except Exception:
        pass
    deadline = time.monotonic() + (settings.human_timeout if timeout is None else timeout)
    while time.monotonic() < deadline:
        browser.wait(1500)
        if os.path.exists(done_flag):
            os.remove(done_flag)
            break
        visible = read()
        if until is not None:
            if any(_contains(" ".join(visible), want) for want in _labels(until)):
                break
        elif not blocker(visible):
            break
    else:
        raise VisorError(f"HUMAN_NEEDED timed out: {reason}")
    print("[HUMAN_DONE] Continuing.")
    browser.settle(timeout=4.0)
    return True


# ── Session / tabs (thin wrappers so flows only need `import visor`) ─────────

def current_url() -> str:
    return browser.get_page().url


def page():
    """The underlying Playwright page, for anything visor doesn't cover. Off in OCR-only mode."""
    if settings.ocr_only:
        raise VisorError("visor.page() is off in OCR-only mode (VISOR_OCR_ONLY=1): read the page with "
                         "visor.read(), visor.text(), visor.see() or visor.find() instead")
    return browser.get_page()
