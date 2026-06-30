"""
Visor Extractor Primitive

Extracts structured data from a page via DOM schemas or LLM vision.
"""
from visor.core import browser

def extract_dom(schema: dict, container_selector: str = "body") -> list:
    """
    Extract structured data purely via the DOM by executing JS.
    schema format: {"Author": ".author-class", "Rating": ".rating-class"}
    Returns a list of dicts.
    """
    page = browser.get_page()
    js_code = """
    ([schema, container_sel]) => {
        const containers = document.querySelectorAll(container_sel);
        const results = [];
        for (let c of containers) {
            let item = {};
            for (let [key, selector] of Object.entries(schema)) {
                let el = c.querySelector(selector);
                item[key] = el ? el.innerText.trim() : null;
            }
            results.push(item);
        }
        return results;
    }
    """
    return page.evaluate(js_code, [schema, container_selector])

def extract(schema: dict, container_selector: str = "body", use_llm: bool = False) -> list:
    """
    Unified extraction interface.
    """
    if use_llm:
        # Placeholder for external LLM vision integration
        print("[EXTRACTOR] LLM extraction requested but no provider configured. Falling back to DOM.")
    return extract_dom(schema, container_selector)
