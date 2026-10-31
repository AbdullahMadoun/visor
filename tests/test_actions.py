"""Button handling end to end: headless Chromium + real OCR on local pages."""
import time

import pytest

from conftest import page_url, log_text

pytestmark = pytest.mark.browser


def test_clicks_a_word_inside_a_line_of_links(shop):
    shop.click("About us")
    assert log_text() == "nav:About us"


def test_prefers_the_button_over_the_same_word_in_body_text(shop):
    shop.click("Checkout")
    assert log_text() == "checkout"


def test_near_picks_the_right_duplicate(shop):
    shop.click("Add to cart", near="Blue mug")
    assert log_text() == "added:Blue mug"


def test_index_picks_by_reading_order(shop):
    shop.click("Add to cart", index=1)
    assert log_text() == "added:Blue mug"
    shop.click("Add to cart", index=0)
    assert log_text() == "added:Red mug"


def test_alternatives_take_the_first_that_is_visible(shop):
    hit = shop.click(["Buy now", "Checkout"])
    assert hit["label"] == "Checkout" and log_text() == "checkout"


def test_waits_for_a_disabled_button_to_enable(live):
    import visor
    visor.goto(page_url("late.html"))
    start = time.monotonic()
    visor.click("Pay now")
    assert log_text() == "paid"
    assert time.monotonic() - start >= 1.0  # it really waited


def test_reports_a_button_that_never_enables(live):
    import visor
    visor.goto(page_url("late.html"))
    with pytest.raises(visor.ElementDisabled):
        visor.click("Pay now", timeout=0.8)


def test_icon_only_button_found_by_accessible_name(shop):
    shop.click("Settings")
    assert log_text() == "settings"


def test_scrolls_to_a_button_below_the_fold(shop):
    shop.click("Load more")
    assert log_text() == "loaded more"


def test_missing_text_fails_fast_with_what_was_visible(shop):
    start = time.monotonic()
    with pytest.raises(shop.TextNotFound) as err:
        shop.click("Definitely not on this page", scroll=False)
    assert time.monotonic() - start < 5  # a static screen doesn't burn the whole timeout
    assert "Add to cart" in err.value.visible


def test_fill_by_label_placeholder_and_select(shop):
    shop.fill("Email address", "me@example.com")
    shop.fill("Search products", "mugs")
    shop.fill("Country", "Jordan")
    page = shop.page()
    assert page.input_value("#email") == "me@example.com"
    assert page.input_value("#search") == "mugs"
    assert page.input_value("#country") == "Jordan"
    shop.fill("Search products", "cups")  # replaces, not appends
    assert page.input_value("#search") == "cups"


def test_follows_a_new_tab_and_returns_when_it_closes(shop):
    shop.click("Open help")
    assert shop.see("Help center")
    shop.close_tab()
    assert "shop.html" in shop.current_url()


def test_covered_button_closes_the_overlay_first(live):
    import visor
    visor.goto(page_url("consent.html"))
    visor.click("Continue reading")
    assert log_text() == "continued"
    assert visor.page().title() == "rejected"  # privacy-friendly choice first


def test_expect_verifies_the_outcome(shop):
    shop.click("Checkout", expect="checkout")
    with pytest.raises(shop.TextNotFound):
        shop.click("Checkout", expect="Order confirmed", timeout=1)


def test_wait_for_and_wait_gone(live):
    import visor
    visor.goto(page_url("loading.html"))
    assert visor.see("Loading results")
    assert visor.wait_for("Results ready", timeout=6)["text"] == "Results ready"
    assert visor.wait_gone("Loading results", timeout=2)


def test_read_returns_lines(shop):
    lines = shop.read()
    assert any("Add to cart" in line for line in lines)
    assert "Red mug" in shop.text()


def test_runner_click_path_uses_the_same_button_logic(shop):
    from visor.core import runner
    assert runner.ocr_find_and_click("Checkout", shop.current_url(), "test_flow") == "success"
    assert log_text() == "checkout"


def test_check_reads_state_first(live):
    import visor
    visor.goto(page_url("form.html"))
    page = visor.page()
    visor.check("Remember me")                 # styled checkbox: the real input is invisible
    assert page.is_checked("#remember")
    visor.check("Remember me")                 # already on: must not flip back
    assert page.is_checked("#remember")
    visor.check("Remember me", on=False)
    assert not page.is_checked("#remember")
    visor.check("Send me news")                # unlabelled box next to its text
    assert page.is_checked("#news")
    visor.check("Professional")                # radio
    assert page.is_checked("#pro") and not page.is_checked("#basic")


def test_select_in_a_custom_dropdown(live):
    import visor
    visor.goto(page_url("form.html"))
    visor.select("Choose a color", "Green")
    assert visor.page().text_content("#picker") == "Green"


def test_upload_and_download(live, tmp_path):
    import visor
    visor.goto(page_url("form.html"))
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4 test")
    visor.upload("Upload resume", str(resume))
    assert log_text() == "resume.pdf"
    saved = visor.download("Export report", save_to=str(tmp_path / "report.txt"))
    assert open(saved).read() == "hello visor"


def test_heals_inside_run_flow_with_the_strategy_tree(live, tmp_path):
    import visor
    from visor.core import runner
    from visor.strategy import tree
    tree.save({"heal_test": {"find_Buy_now": {"not_found": {
        "Add_to_cart_visible": {"action": "skip", "reason": "no buy button on this layout"}}}}})

    def flow(url):
        visor.goto(url)
        visor.click("Buy now", timeout=1, scroll=False)  # not on the page → tree says skip
        return "success"

    results = runner.run_flow(flow, [page_url("shop.html")], str(tmp_path / "r.csv"), flow_key="heal_test")
    assert list(results.values()) == ["skipped:no buy button on this layout"]
    tree.save({})


def test_link_click_waits_for_the_next_page(live):
    import visor
    visor.goto(page_url("nav.html"))
    hit = visor.click("Go to help")
    assert hit["effect"] == "navigated"
    assert visor.current_url().endswith("help.html")
    assert visor.see("Help center")  # no waiting needed: click already let the new page settle


def test_blocker_detection():
    from visor.core import actions
    assert actions.blocker(["Please verify you're human"]) == "verify you're human"
    assert actions.blocker(["Enter the verification code we sent"]) == "verification code"
    assert actions.blocker(["Add to cart", "Checkout"]) is None


def test_human_handshake_waits_for_the_captcha_to_be_solved(live, monkeypatch):
    import visor
    monkeypatch.setattr(visor.settings, "headless", False)  # pretend a person can see the window
    visor.goto(page_url("captcha.html"))
    visor.click("Continue to site", timeout=1)
    assert log_text() == "through"


def test_human_handshake_refuses_in_headless(live):
    import visor
    visor.goto(page_url("captcha.html"))
    with pytest.raises(visor.VisorError, match="HUMAN_NEEDED"):
        visor.human_handshake("captcha")


def test_dom_fallback_never_clicks_an_element_hidden_under_another(live):
    # Found on LinkedIn: "View profile" existed only as an accessible name, under the menu's
    # "Language" item; clicking its centre opened language settings.
    import visor
    visor.goto(page_url("covered.html"))
    with pytest.raises(visor.TextNotFound):
        visor.click("View profile", timeout=2, scroll=False)
    assert log_text() == ""
    visor.click("Open settings", timeout=2)  # an uncovered icon button still works
    assert log_text() == "settings"
