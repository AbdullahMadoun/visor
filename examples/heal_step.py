import os
import json
import time
from playwright.sync_api import sync_playwright

def heal():
    project_root = os.path.dirname(os.path.abspath(__file__))
    failure_path = os.path.join(project_root, "agent_handshake", "failure.json")
    fix_path = os.path.join(project_root, "agent_handshake", "fix.json")
    if not os.path.exists(failure_path):
        print("No failure.json found")
        return
        
    with open(failure_path) as f:
        data = json.load(f)
        
    print(f"Healing step: {data.get('step')}")
        
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
            context = browser.contexts[0]
            page = context.pages[0]
            
            text = page.locator("body").inner_text().lower()
            
            # 0. Check if job is expired or already applied
            if "no longer accepting applications" in text or "application submitted" in text:
                print("Job expired or already applied. Skipping.")
                with open(fix_path, "w") as f:
                    json.dump({"action": "skip", "reason": "expired_or_applied"}, f)
                return
                
                
            # 2. Easy Apply
            btn = page.locator("button.jobs-apply-button--top-card, button[aria-label*='Easy Apply']").first
            if btn.is_visible():
                print("Clicking Easy Apply")
                btn.evaluate("el => el.click()")
                time.sleep(2)
                
            # 3. Form fields (Text, Radios, Selects)
            # Require strict knowledge bank verification
            # Since the knowledge bank is not yet populated, we will skip if there are ANY unfilled required fields
            
            unfilled_inputs = []
            
            # Only check for inputs if the modal is actually open
            modal = page.locator(".artdeco-modal__content, .jobs-easy-apply-modal__content").first
            if modal.is_visible():
                for inp in modal.locator("input[type='text'], input[type='number']").all():
                    if inp.is_visible() and not inp.input_value():
                        unfilled_inputs.append("text_input")
                        
                for fs in modal.locator("fieldset").all():
                    if fs.is_visible() and fs.locator("input[type='radio']").count() > 0:
                        if not fs.locator("input[type='radio']:checked").count():
                            unfilled_inputs.append("radio_group")
                            
                for s in modal.locator("select").all():
                    if s.is_visible() and s.input_value() == "Select an option":
                        unfilled_inputs.append("dropdown")
                    
            if unfilled_inputs:
                print(f"ESCALATION: Form contains unfilled fields: {unfilled_inputs}.")
                print("Missing knowledge bank data! Agent must wake up, check Obsidian, and fill it manually.")
                import sys
                sys.exit(1)
                    
            # 6. Scroll the modal down in case elements are hidden
            try:
                page.evaluate("""
                    const modals = document.querySelectorAll(".artdeco-modal__content, .jobs-easy-apply-modal__content, .pb4");
                    for (let m of modals) { m.scrollTo(0, m.scrollHeight); }
                """)
                time.sleep(1)
            except: pass

            # 7. Next / Review / Submit
            # Only do this if the agent stalled on a form step
            if "stalled" in data.get("step", ""):
                action_btns = page.locator("button:visible:has-text('Next'), button:visible:has-text('Review'), button:visible:has-text('Submit')").all()
                clicked_action = False
                for btn in action_btns:
                    if btn.is_visible():
                        print(f"Clicking Next/Review/Submit: {btn.inner_text().strip()}")
                        btn.evaluate("el => el.click()")
                        clicked_action = True
                        time.sleep(2)
                        break
                        
                if not clicked_action:
                    print("STILL NO BUTTON. Form is unrecoverable. Clearing state with skip.")
                    with open(fix_path, "w") as f:
                        json.dump({"action": "skip", "reason": "no_action_button"}, f)
                    return
            else:
                print("Step was not a stalled form, finished healing.")
                
        except Exception as e:
            err_str = str(e)
            print(f"Error during playwright healing: {err_str}")
            if "closed" in err_str.lower() or "econnrefused" in err_str.lower() or "timeout" in err_str.lower() or "list index out of range" in err_str.lower():
                print("Browser is closed, unavailable, or timed out. Clearing state with skip and continuing.")
                with open(fix_path, "w") as f:
                    json.dump({"action": "skip", "reason": "browser_error"}, f)
                return
            import sys
            sys.exit(1)

    with open(fix_path, "w") as f:
        json.dump({"action": "resume"}, f)
    print("Wrote fix.json")

if __name__ == "__main__":
    heal()
