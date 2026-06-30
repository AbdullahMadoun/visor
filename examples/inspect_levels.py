from playwright.sync_api import sync_playwright

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        url = "https://www.google.com/maps/search/best+coffee+in+Sulimaniyah+Riyadh/?hl=en"
        print(f"Navigating to: {url}")
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        
        js_code = """
        () => {
            const link = document.querySelector('a.hfpxzc');
            if (!link) return "No link found";
            
            const info = [];
            let current = link;
            for (let i = 0; i < 6; i++) {
                if (current) {
                    info.push({
                        level: i,
                        tagName: current.tagName,
                        className: current.className,
                        innerTextLength: current.innerText ? current.innerText.length : 0,
                        innerText: current.innerText ? current.innerText.substring(0, 200) : ''
                    });
                    current = current.parentElement;
                }
            }
            return info;
        }
        """
        levels = page.evaluate(js_code)
        import json
        print(json.dumps(levels, indent=2))
        browser.close()

if __name__ == "__main__":
    main()
