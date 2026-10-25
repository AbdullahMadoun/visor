# Contributing to Visor

Thanks for considering a contribution!

## 🛠 Project Structure

- `src/visor/core/actions.py`: finding things by visible text and acting on them (`click`, `fill`, `check`, …).
- `src/visor/core/ocr.py`: perception. OCR engines, word/line/phrase layout, text matching.
- `src/visor/core/browser.py`: browser lifecycle, tabs, sessions, visual settling.
- `src/visor/core/runner.py`: running flows over targets, the strategy tree and the agent handshake.
- `src/visor/strategy/`: the strategy tree.
- `src/visor/platforms/`: platform-specific flows (kept out of git).
- `src/visor/cli.py`: the `visor` command.

## 💻 Local Development Setup

1. Fork and clone the repo.
2. Install in editable mode, plus the browser:
   ```bash
   pip install -e ".[dev]"
   playwright install chromium
   ```
3. Make your changes in a new branch.

## 🧪 Testing

```bash
pytest
```

The suite runs headless against local pages in `tests/pages/` and needs no internet. It uses a throwaway workspace and never attaches to your own Chrome. Browser tests are skipped automatically when Chromium or an OCR engine is missing. When you add a feature that handles a new kind of page element, add a small page under `tests/pages/` and a test that clicks it for real.

## 🚀 Adding a Flow

Write a Python file with a `main(target)` function that uses the `visor` API, and run it with `visor run --flow your_flow.py --targets targets.csv`. Return `"success"`, `"failed"` or `"skipped:<reason>"`, return nothing for success, or raise `visor.Skip("reason")`.

## 🤝 Submitting a PR

- Keep your PRs focused on a single change.
- Ensure `pytest` passes locally.
- Include a summary of your changes in the PR description.
