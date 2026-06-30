import threading
import time
from visor.core import browser, recorder

def run_test():
    # Run the recorder in a separate thread
    print("Starting recorder thread...")
    t = threading.Thread(target=recorder.start_recording, args=("test_flow", "https://example.com", "Test"))
    t.daemon = True
    t.start()
    
    time.sleep(5)  # Wait for it to launch
    
    # Get the page
    page = browser.get_page()
    print("Test script got page:", page.url)
    
    # Check if button exists
    btn_exists = page.evaluate("!!document.getElementById('visor-stop-btn')")
    print("Button exists:", btn_exists)
    
    if btn_exists:
        print("Clicking stop button via playwright...")
        page.click("#visor-stop-btn", force=True)
        time.sleep(2)
        print("Thread is_alive:", t.is_alive())
    else:
        print("Button not found!")
        
    browser.close()

if __name__ == "__main__":
    run_test()
