# Visor 👁️

**A production-grade, self-healing browser automation harness that ignores the DOM and relies entirely on visual perception.**

Visor is a contrarian take on AI web automation. While most of the industry relies on extracting massive, messy DOM trees and passing them to LLMs for zero-shot decision-making, **Visor reads the screen visually via OCR** and injects low-level CDP clicks. 

When things break, it autonomously updates its own persistent `tree.json` logic map—meaning it learns from UI changes and **never makes the same mistake twice**.

## Why Visor?

While generalized AI agents are great for open-ended requests (like "go buy me a t-shirt"), Visor is designed for people looking to automate **specific, repeatable, action-based tasks**.

- **Visual Perception**: Instead of parsing massive, messy DOM trees that break when class names change, Visor looks at the screen geometrically using local OCR. It interacts with the UI exactly how a human does.
- **Speed & Efficiency**: By executing fast, deterministic Python code 95% of the time, Visor avoids expensive and slow LLM API calls on every single click. It only wakes up the AI when it encounters an unknown failure.
- **Self-Healing Memory**: When Visor gets stuck, it pauses. An agent diagnoses the issue and updates a persistent `tree.json` strategy file. Visor learns the fix and never makes the same mistake twice.

---

## 🧠 How the Self-Healing Architecture Works

Visor uses a deterministic execution loop backed by an AI-healer handshake.

1. **Deterministic Execution:** You write simple flows in Python (e.g., "Find the 'Connect' button and click it"). Visor takes a screenshot, runs OCR to find the text, and clicks the geometric center of the bounding box via CDP.
2. **The Breakage:** The website updates its UI (e.g., "Connect" is changed to "Follow"). The deterministic script fails to find "Connect".
3. **The Agent Handshake (`AGENT_NEEDED`):** Instead of crashing, the script pauses. It writes a `failure.json` payload containing the screenshot, the current OCR extraction, and the target it was looking for.
4. **The Healing:** An external LLM agent (like Claude Desktop or Gemini) reads the failure context, visually identifies the new button ("Follow"), and writes a fix to `agent_handshake/fix.json`.
5. **The Memory (`tree.json`):** The LLM not only fixes the current session, but permanently mutates Visor's `strategy/tree.json`. The next time Visor runs, it checks the tree *before* executing the old code, successfully finding "Follow" without needing the LLM again.

---

## 🚀 Quickstart

### 1. Install Visor

```bash
git clone https://github.com/your-username/visor.git
cd visor
pip install -e .
```

*Note for Mac Users: Visor will automatically detect and use Apple's native Vision API (`ocrmac`) for lightning-fast, highly accurate screen perception.*

### 2. Run a Workflow

Execute one of your pre-built platform flows:

```bash
visor --flow linkedin_connect --targets data/my_targets.csv
```

### 3. Review the Live Strategy Tree

To see exactly what your agent has learned and saved to memory:

```bash
python3 src/visor/strategy/tree.py
```

## 📂 Directory Structure

Visor strictly separates source code from runtime artifacts to ensure zero data leakage.

- `src/visor/`: The core execution engine (browser, ocr, clicker) and platform-specific flows.
- `visor_workspace/`: **(Ignored in Git)** Your private runtime artifacts.
  - `agent_handshake/`: Where Visor and the LLM agent exchange failure contexts and fixes.
  - `videos/`: Automatically recorded MP4s of your browser sessions.
  - `logs/failures/`: Screenshots of the exact moment a flow failed.

## License
MIT
