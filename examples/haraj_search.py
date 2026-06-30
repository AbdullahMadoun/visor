import time
from visor.core.browser import navigate, screenshot, close
from visor.core.ocr import summarize

print("Navigating to Haraj...")
navigate("https://haraj.com.sa/")
time.sleep(5)
path = screenshot("/tmp/haraj_home.png")
print(f"Screenshot saved to {path}")
texts = summarize(path)
print("OCR Texts:", texts)
close()
