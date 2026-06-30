# General Architectural Insights

This document outlines the core technical insights and geometric strategies behind the `autobot` visual automation framework.

## 1. Viewport & Coordinate Matching

- **Absolute Pixels**: Clicks and typings are executed at absolute pixel coordinates relative to the Playwright viewport width and height (default: 1440x900).
- **CDP Input Injection**: Interaction coordinates bypass the Playwright DOM actionability checks and are injected directly into Chromium's Blink rendering engine using raw Chrome DevTools Protocol (CDP) commands:
  ```python
  page.mouse.click(x, y)
  ```
  This is highly robust because it bypasses overlay filters and executes natively as an operating system event inside the page.
- **DPR Scaling Immunity**: Viewport coordinates matching OCR bounding boxes are completely immune to macOS Display Scaling (Retina DPR Scaling factors like 2.0x) because the screenshot and coordinates are normalized within Chromium's internal rendering grid (1440x900 viewport space), rather than the physical host screen coordinates.
- **Pixel Coordinates are Absolute Truth**: If the OCR or click logs say `pixel(1633,747)` and the screen is 2084px wide, that means it's 78% from the left (likely a right-hand sidebar). Always read the numbers and trust the math, don't guess based on text labels alone.

## 2. Dual-Engine OCR Coordinate Conversions

- **Darwin (macOS)**: Uses the native hardware-accelerated Apple Vision Framework via `ocrmac` for lightning-fast OCR.
  - *Origin Difference*: The Apple Vision API uses normalized ratio coordinates (0.0 to 1.0) with the **bottom-left** as the origin (0,0).
  - *Conversion*: The coordinates must be multiplied by image width and height, and inverted along the Y-axis to map to Chromium's **top-left** (0,0) origin:
    ```python
    x = bbox_x_ratio * img_width
    y = (1.0 - (bbox_y_ratio + bbox_h_ratio)) * img_height
    ```
- **Fallback Platforms**: Uses PyTorch-based `easyocr` which returns absolute pixel bounding boxes directly relative to the top-left origin.

## 3. Geometric Anchor Strategy

To prevent visual drift or clicking the wrong element when the same label appears multiple times (e.g. common headers, sidebar options, or footer links):

### Anchor-Based Bounding Boxes (`ocr.find`)
- **Principle**: Filter OCR candidate coordinates using relative visual anchors or DOM-extracted bounding boxes instead of hardcoded coordinates.
- **DOM Bounds Filtering**: Extracted via `page.locator(selector).bounding_box()` to constrain the OCR search zone:
  ```python
  match = ocr.find("TargetLabel", img_path, bounds=bounds)
  ```
- **Anchor Neighbors**: Identify a unique neighbor element on the same horizontal row (Y-tolerance filter) or vertical column (X-tolerance filter) to isolate the target button:
  ```python
  match = ocr.find("TargetLabel", img_path, anchor_labels=["NeighborLabel"], y_tolerance=80)
  ```

### Radius-Based Proximity (`ocr.find_near`)
- **Principle**: When a dropdown, popover, or modal opens, look for options specifically within a defined radius of the last clicked location.
  ```python
  match = ocr.find_near("DropdownOption", img_path, near_x=last_x, near_y=last_y, radius=400)
  ```

### OCR Confidence and Strictness
- **Long Text Strings**: Long button labels or sentences get naturally lower OCR confidence scores (e.g., 0.75). Setting `min_conf` strictness too high (e.g., 0.8) causes silent failures where buttons exist but are ignored. Keep the default at a reasonable threshold (e.g., 0.6) for sentences.

## 4. The Strategy Tree Philosophy

- **VLM vs. Strategy Tree**: Tools that stream every frame to a VLM burn massive token budgets. `autobot` follows a "figure it out once, execute deterministically" approach.
- **Deterministic Loop**: The agent writes the core Python execution loop and seeds `tree.json` with visual adjustments. During normal runs, the Python code and a fast OCR layer execute instantly.
- **Self-Healing Loop**: The AI agent is only called as the "brain part" when the execution engine hits a visual state it does not recognize. The agent identifies the new visual signature, mutates `tree.json` to handle the new branch, and restarts the task to heal the flow.
