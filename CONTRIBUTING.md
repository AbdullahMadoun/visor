# Contributing to Autobot 🤖

First off, thank you for considering contributing to Autobot! It's people like you that make Autobot such a great tool.

## 🛠 Project Structure

- `src/autobot/core/`: The heart of the engine (browser connection, OCR logic, CDP clickers, the main orchestrator).
- `src/autobot/strategy/`: The heuristic strategy logic.
- `src/autobot/platforms/`: Platform-specific scripts (e.g., LinkedIn, Maps).
- `src/autobot/cli.py`: The entry point for the `autobot` CLI command.

## 💻 Local Development Setup

1. Fork and clone the repo.
2. Install in editable mode:
   ```bash
   pip install -e ".[dev]"
   ```
3. Make your changes in a new branch.

## 🧪 Testing

We rely on workflow tests rather than just unit tests. To test your changes, run:
```bash
pytest tests/
```
Ensure your Chromium debugger is running before launching tests:
```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222
```

## 🚀 Adding a New Platform

1. Create a directory under `src/autobot/platforms/your_platform/`.
2. Write a script that exposes a function `def main(target: str) -> str:`.
3. Your function should return `"success"`, `"failed"`, or `"skipped"`.

## 🤝 Submitting a PR

- Keep your PRs focused on a single change.
- Ensure all workflow tests pass locally.
- Include a summary of your changes in the PR description.
