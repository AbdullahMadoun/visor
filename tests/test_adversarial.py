"""Adversarial pages: each reproduces a failure from early real-world runs.

Every test checks what actually happened on the page (DOM state or the page's own log),
never just what Visor reported, because the original bugs were all clicks that "worked".
"""
import pytest

from conftest import page_url, log_text

pytestmark = pytest.mark.browser


def _step():
    import visor
    return visor.page().evaluate("document.getElementById('step').textContent")


def _quick(monkeypatch, timeout=3):
    """No agent waits and short OCR timeouts, so a failing flow fails fast."""
    from visor.config import settings
    monkeypatch.setattr(settings, "agent", False)
    monkeypatch.setattr(settings, "timeout", timeout)


# ── 1. A sidebar "Next" next to a multi-step form's "Next" ───────────────────

@pytest.fixture
def wizard(live):
    import visor
    visor.goto(page_url("adv_sidebar_next.html"))
    assert _step() == "Step 1/3"
    return visor


def test_near_the_form_heading_advances_the_form(wizard):
    wizard.click("Next", near="Create your account")
    assert _step() == "Step 2/3"
    assert log_text() == "form:step 2"


def test_expect_never_reports_success_while_the_form_is_stuck(wizard):
    # Either the form advances, or Visor raises; a "successful" click that left the form on 1/3
    # is the original bug.
    try:
        wizard.click("Next", expect="2/3", timeout=3)
    except wizard.TextNotFound:
        assert _step() == "Step 1/3"
        return
    assert _step() == "Step 2/3", f"click reported success but the page says {_step()!r} (log: {log_text()!r})"


def test_expect_is_not_satisfied_by_a_date_that_contains_the_digits(live):
    # Same trap, plus "Posted Oct 23, 2023" in the sidebar: "2/3" normalises to "2 3", and "23"
    # must not count as the step indicator having changed.
    import visor
    visor.goto(page_url("adv_sidebar_next.html") + "?dates=1")
    try:
        visor.click("Next", expect="2/3", timeout=3)
    except visor.TextNotFound:
        assert _step() == "Step 1/3"
        return
    assert _step() == "Step 2/3", f"click reported success but the page says {_step()!r} (log: {log_text()!r})"


def test_plain_next_prefers_the_form_button_over_the_sidebar_link(wizard):
    # No hints at all: what a first-time user writes. The sidebar link comes first in reading order.
    wizard.click("Next")
    assert log_text() == "form:step 2"


def test_near_the_sidebar_heading_still_picks_the_sidebar_link(wizard):
    # The fix must not hard-code "main beats sidebar": an anchor in the sidebar wins it back.
    wizard.click("Next", near="Help articles")
    assert log_text() == "sidebar:Next"
    assert _step() == "Step 1/3"


def test_a_sidebar_only_label_is_still_clicked(wizard):
    # Losing ties is all the sidebar penalty does; a label found only in the sidebar is clicked.
    wizard.click("Previous")
    assert log_text() == "sidebar:Previous"


# ── 2. A goal that flashes on screen and vanishes ────────────────────────────

def _save_flow(url):
    import visor
    visor.goto(url)
    visor.click("Save")


def _update_flow(url):
    import visor
    visor.goto(url)
    visor.click("Update")


def _run_save(tmp_path, monkeypatch, query="", flow=_save_flow):
    from visor.core import runner
    _quick(monkeypatch)
    target = page_url("adv_flash.html") + query
    results = runner.run_flow(flow, [target], str(tmp_path / "r.csv"), goal="Saved")
    assert log_text() == "clicked"  # the click itself did land
    return results[target]


def test_flashing_goal_is_not_success(live, tmp_path, monkeypatch):
    assert _run_save(tmp_path, monkeypatch) == "failed"


def test_goal_is_not_met_by_the_button_that_shares_its_word(live):
    # Nothing clicked, "Saved" is not on screen. A fuzzy match may still aim a click at "Save",
    # but as proof (goals, expect=) it must not count.
    import visor
    visor.goto(page_url("adv_flash.html"))
    assert visor.page().evaluate("document.getElementById('status').textContent") == ""
    assert visor.see("Saved")  # OCR-misread tolerance, fine for aiming
    assert not visor.see("Saved", proof=True)
    from visor.core import runner
    assert not runner.goal_met("Saved", timeout=1)


def test_flashing_goal_is_not_success_when_the_button_reads_differently(live, tmp_path, monkeypatch):
    # The flash check itself (goal_met looks twice, 800 ms apart), without the Save/Saved look-alike
    assert _run_save(tmp_path, monkeypatch, "?button=Update", _update_flow) == "failed"


def test_goal_that_stays_is_success(live, tmp_path, monkeypatch):
    assert _run_save(tmp_path, monkeypatch, "?stay=1") == "success"


def test_goal_that_stays_is_success_when_the_button_reads_differently(live, tmp_path, monkeypatch):
    assert _run_save(tmp_path, monkeypatch, "?stay=1&button=Update", _update_flow) == "success"


# ── 3. Two cards, each with its own "Connect" ────────────────────────────────

def _buttons():
    import visor
    return visor.page().evaluate(
        "['card-lina', 'card-omar'].map(id => document.querySelector('#' + id + ' button').textContent)")


@pytest.fixture
def people(live):
    import visor
    visor.goto(page_url("adv_two_cards.html"))
    assert _buttons() == ["Connect", "Connect"]
    return visor


def test_near_name_connects_only_that_person(people):
    people.click("Connect", near="Omar Saleh")
    assert _buttons() == ["Connect", "Pending"]
    assert log_text() == "connect:Omar Saleh"


def test_near_first_name_connects_only_that_person(people):
    people.click("Connect", near="Lina Haddad")
    assert _buttons() == ["Pending", "Connect"]
    assert log_text() == "connect:Lina Haddad"


# ── 4. "Free Shipping by Amazon" among "Shipping: $5.99" and "Shipping policy" ─

@pytest.fixture
def catalog(live):
    import visor
    visor.goto(page_url("adv_shipping.html"))
    return visor


def test_click_full_phrase_hits_the_free_shipping_item(catalog):
    catalog.click("Free Shipping by Amazon")
    assert log_text() == "picked:Bamboo cutting board"


def test_find_full_phrase_lands_inside_the_free_shipping_item(catalog):
    hit = catalog.find("Free Shipping by Amazon", timeout=3)
    assert hit is not None
    box = catalog.page().evaluate(
        "(() => { const r = document.getElementById('item-board').getBoundingClientRect();"
        " return [r.left, r.top, r.right, r.bottom]; })()")
    assert box[0] <= hit["x"] <= box[2] and box[1] <= hit["y"] <= box[3], (hit, box)


def test_bare_shipping_is_ambiguous(catalog):
    # Documents the "widened target" risk: a label shortened to "Shipping" matches every item's
    # shipping line and the policy links, so a flow must use the full phrase (or near=/region=).
    hits = catalog.find_all("Shipping")
    assert len(hits) > 1, [h["text"] for h in hits]


# ── 5. A confirm modal that sometimes never appears ──────────────────────────

def _send_flow(url):
    import visor
    visor.goto(url)
    visor.click("Send")
    visor.click("Confirm")


def test_modal_path_reaches_the_goal(live, tmp_path, monkeypatch):
    from visor.core import runner
    _quick(monkeypatch)
    target = page_url("adv_late_modal.html")
    results = runner.run_flow(_send_flow, [target], str(tmp_path / "r.csv"), goal="Pending")
    assert log_text() == "confirmed"
    assert results[target] == "success"


def test_flow_raises_when_the_modal_is_skipped(live, monkeypatch):
    import visor
    _quick(monkeypatch)
    with pytest.raises(visor.TextNotFound):
        _send_flow(page_url("adv_late_modal.html") + "?direct=1")
    assert log_text() == "send"


def test_goal_on_screen_beats_the_missing_confirm(live, tmp_path, monkeypatch):
    from visor.core import runner
    _quick(monkeypatch)
    target = page_url("adv_late_modal.html") + "?direct=1"
    results = runner.run_flow(_send_flow, [target], str(tmp_path / "r.csv"), goal="Pending")
    assert log_text() == "send"  # Confirm never existed; the script did raise
    assert results[target] == "success"
