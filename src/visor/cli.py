"""
visor entry point.

Usage:
  visor --flow my_flow.py --targets targets.csv    run a flow over every target (same as `visor run`)
  visor run --flow my_flow.py --url https://...     run a flow on one or more URLs
  visor record --flow name --url URL [--goal TEXT]   do a task once; get a flow that ends on your goal
  visor login https://example.com                    log in by hand once; later runs reuse the session
  visor ocr [image.png | --url URL] [--find TEXT]    print what visor sees
  visor tree [--serve [--port N]]                    show the learned strategy tree (--serve: live map in the browser)
  visor doctor                                       check the installation
"""

import argparse
import sys
import os
import csv

# Enforce unbuffered I/O for daemonized/human-in-the-loop workflows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(line_buffering=True)
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(line_buffering=True)

from visor.config import configure, settings
from visor.core import WORKSPACE_DIR

COMMANDS = ("run", "record", "login", "ocr", "tree", "doctor")


def load_targets(path: str) -> list:
    """Targets from a CSV (column 'target', 'url', or the first one) or a text file (one per line)."""
    targets = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        if not path.lower().endswith(".csv"):
            return [line.strip() for line in f if line.strip() and not line.lstrip().startswith("#")]
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        target_col = "target" if "target" in fieldnames else ("url" if "url" in fieldnames else (fieldnames[0] if fieldnames else "target"))
        for row in reader:
            val = (row.get(target_col) or "").strip()
            status = (row.get("status") or "pending").strip()
            # Exclude any success or any skipped variant (skipped:reason)
            if val and status != "success" and not status.startswith("skipped"):
                targets.append(val)
    return targets


def load_flow(flow: str):
    """Import a flow by file path or platform name; returns its entry function."""
    import importlib

    # Allow loading flows directly by Python file path
    is_file = flow.endswith(".py") or os.path.isfile(flow)
    if is_file:
        import importlib.util
        flow_stem = os.path.splitext(os.path.basename(flow))[0]
        # Prefixed so a flow file called e.g. json.py can't shadow a real module
        module_name = f"visor_user_flow_{flow_stem}"
        spec = importlib.util.spec_from_file_location(module_name, flow)
        if spec is None:
            raise FileNotFoundError(f"No flow file at {flow}")
        module = importlib.util.module_from_spec(spec)
        # Registered so restart_flow can hot-reload it (see runner._reload_module)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    elif "_" in flow:
        platform, flow_name = flow.split("_", 1)
        module_name = f"visor.platforms.{platform}.{flow_name}"
        module = importlib.import_module(module_name)
    else:
        module_name = f"visor.platforms.{flow}.main"
        module = importlib.import_module(module_name)

    # Store for Python hot-reloading (restart_flow action)
    import visor.core.runner as runner
    runner._active_module = module

    # By convention, find the function with a standard name
    flow_fn = getattr(module, "main",
                      getattr(module, "run",
                              getattr(module, "run_task", None)))

    # Fallback to dynamically guessed names for legacy compatibility
    if not flow_fn:
        flow_id = flow_stem if is_file else flow
        flow_fn_name = flow_id.split("_", 1)[1] if "_" in flow_id else flow_id
        last_segment = flow_id.split("_")[-1]
        flow_fn = getattr(module, flow_id,
                          getattr(module, flow_fn_name, getattr(module, last_segment, None)))

    if not callable(flow_fn):
        raise AttributeError(f"Could not find callable entry point (main/run/run_task) in {module_name}")
    return flow_fn


def _pace(value: str) -> tuple:
    low, _, high = value.partition("-")
    return (float(low), float(high or low))


def cmd_run(argv: list) -> int:
    parser = argparse.ArgumentParser(prog="visor run", description="Run a flow over a list of targets")
    parser.add_argument("--flow", required=True, help="Flow to run (./path/to/flow.py or platform_flow)")
    parser.add_argument("--targets", help="CSV (column 'target' or 'url') or .txt file, one target per line")
    parser.add_argument("--url", action="append", default=[], help="A target URL (repeatable)")
    parser.add_argument("--retries", type=int, default=1, help="Max retry loops until 100%% success")
    parser.add_argument("--headless", action="store_true", help="Run the browser without a window")
    parser.add_argument("--no-agent", action="store_true", help="Fail unknown steps instead of waiting for fix.json")
    parser.add_argument("--agent-timeout", type=float, help="Seconds to wait for an agent fix (default 600)")
    parser.add_argument("--pace", type=_pace, help="Seconds between targets, e.g. 4-9 (default) or 0")
    parser.add_argument("--timeout", type=float, help="Seconds actions keep looking for text (default 8)")
    parser.add_argument("--results", help="Results CSV (default: <workspace>/logs/results.csv)")
    parser.add_argument("--goal", action="append",
                        help="Text that must be on screen when a target is done (repeatable: any of them; "
                             "default: the flow's GOAL)")
    args = parser.parse_args(argv)

    if not args.targets and not args.url:
        parser.error("give --targets FILE or at least one --url")
    if args.headless:
        configure(headless=True)
    if args.no_agent:
        configure(agent=False)
    if args.agent_timeout is not None:
        configure(agent_timeout=args.agent_timeout)
    if args.pace is not None:
        configure(pace=args.pace)
    if args.timeout is not None:
        configure(timeout=args.timeout)

    try:
        flow_fn = load_flow(args.flow)
    except Exception as e:
        print(f"[ERROR] Failed to dynamically load flow '{args.flow}': {e}")
        return 1

    targets = (load_targets(args.targets) if args.targets else []) + args.url
    print(f"[visor] Flow: {args.flow} | Targets: {len(targets)} | Max retries: {args.retries}")

    # Show the live map of what the bot currently knows
    from visor.strategy import tree
    tree.show_map()

    from visor.core.runner import run_flow
    from visor.core import browser
    flow_key = os.path.splitext(os.path.basename(args.flow))[0]
    results_csv = args.results or os.path.join(WORKSPACE_DIR, "logs", "results.csv")
    try:
        run_flow(flow_fn, targets, results_csv, max_retries=args.retries, flow_key=flow_key,
                 goal=args.goal)
    except KeyboardInterrupt:
        return 130
    finally:
        # Clean up browser session
        browser.close()

    print(f"\n[DAEMON] Task complete. Results: {results_csv}")
    return 0


def cmd_record(argv: list) -> int:
    parser = argparse.ArgumentParser(
        prog="visor record",
        description="Do a task once by hand; visor writes it as a flow ending on your goal "
                    "and replays it once to see that it gets there.")
    parser.add_argument("--flow", required=True, help="name of the new flow")
    parser.add_argument("--url", required=True, help="start URL")
    parser.add_argument("--goal", action="append",
                        help="text on screen that means the task is done (asked after recording if missing)")
    parser.add_argument("--description", default="", help="what the task is for (goes in the file)")
    parser.add_argument("--out", help="where to write the flow (default: <flow>.py here)")
    parser.add_argument("--no-verify", action="store_true", help="don't replay the new flow")
    args = parser.parse_args(argv)

    from visor.core import recorder
    out = args.out or f"{args.flow}.py"
    if os.path.exists(out):
        out = f"{os.path.splitext(out)[0]}.recorded.py"
    configure(headless=False)
    trace = recorder.record(args.flow, args.url, args.description)
    if not trace["events"]:
        print("[RECORDER] Nothing was recorded.")
        return 1
    goal = args.goal
    if not goal and sys.stdin.isatty():
        hints = recorder.goal_hints(trace)
        if hints:
            print("[RECORDER] After your last step these appeared: " + ", ".join(repr(h) for h in hints))
        goal = input("[RECORDER] What text on screen means the task is done? (Enter to leave it for later) ").strip()
    if isinstance(goal, list) and len(goal) == 1:
        goal = goal[0]
    status = recorder.write_flow(trace, out, goal=goal or None, verify=not args.no_verify)
    print(f"\n[RECORDER] Wrote {out}. Replay check: {status}")
    print(f"[RECORDER] Run it with: visor run --flow {out} --url URL")
    return 0 if not status.startswith("FAILED") else 1


def cmd_login(argv: list) -> int:
    parser = argparse.ArgumentParser(prog="visor login", description="Log in by hand once and save the session")
    parser.add_argument("url", nargs="?", default="about:blank", help="Login page to open")
    args = parser.parse_args(argv)

    from visor.core import browser
    configure(headless=False, attach=False)  # a window visor owns, so the session can be saved
    browser.init_browser()
    if args.url != "about:blank":
        browser.navigate(args.url)
    try:
        input("\n>>> Log in in the browser window, then press ENTER here to save the session... ")
    except (EOFError, KeyboardInterrupt):
        print("\n[visor] Cancelled; session not saved.")
        browser.close(save=False)
        return 1
    path = browser.save_session()
    browser.close(save=False)
    print(f"[visor] Saved. Later runs start logged in (delete {path} to log out).")
    return 0


def cmd_ocr(argv: list) -> int:
    parser = argparse.ArgumentParser(prog="visor ocr", description="Print the text visor sees, with click coordinates")
    parser.add_argument("image", nargs="?", help="Screenshot to read")
    parser.add_argument("--url", help="Open this page (headless) and read it instead")
    parser.add_argument("--find", help="Also show where this text matches")
    args = parser.parse_args(argv)
    if not args.image and not args.url:
        parser.error("give an image path or --url")

    from visor.core import ocr
    page = None
    image = args.image
    if args.url:
        from visor.core import browser
        configure(headless=True, attach=False, save_session=False)
        browser.navigate(args.url)
        page = browser.get_page()
        image = browser.screenshot()

    for item in ocr.find_all(image, page):
        print(f"{item['x']:5d},{item['y']:5d}  {item['text']}")
    if args.find:
        matches = ocr.find_matches(args.find, image, exact=False, page=page)
        print(f"\n{len(matches)} match(es) for {args.find!r}:")
        for m in matches:
            print(f"  ({m['x']}, {m['y']}) tier={m['tier']} in {m['phrase']!r}")
    if args.url:
        from visor.core import browser
        browser.close(save=False)
    return 0


def cmd_tree(argv: list) -> int:
    parser = argparse.ArgumentParser(prog="visor tree", description="Show the learned strategy tree.")
    parser.add_argument("--serve", action="store_true", help="serve a live, auto-refreshing map in the browser")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args(argv)
    if args.serve:
        from visor.strategy import tree_server
        tree_server.serve(args.port)
        return 0
    from visor.strategy import tree
    tree.show_map()
    return 0


def cmd_doctor(argv: list) -> int:
    """Check that the browser, OCR and workspace all work."""
    import tempfile
    ok = True

    def report(passed: bool, what: str, hint: str = ""):
        nonlocal ok
        ok = ok and passed
        print(f"  {'✓' if passed else '✗'} {what}" + (f"\n      → {hint}" if hint and not passed else ""))

    print("visor doctor\n")
    report(sys.version_info >= (3, 9), f"Python {sys.version.split()[0]}", "visor needs Python 3.9+")
    try:
        os.makedirs(WORKSPACE_DIR, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=WORKSPACE_DIR):
            pass
        report(True, f"Workspace writable: {WORKSPACE_DIR}")
    except OSError as e:
        report(False, f"Workspace writable: {WORKSPACE_DIR}", str(e))

    from visor.core import browser, ocr
    print(f"  • Saved session: {'yes' if os.path.exists(browser.SESSION_FILE) else 'no (run `visor login <url>`)'}")

    configure(headless=True, attach=False, save_session=False)
    try:
        browser.init_browser()
        page = browser.get_page()
        page.set_content("<body style='font:32px Helvetica;padding:40px'><button>Visor works</button></body>")
        report(True, "Chromium launches")
        found = ocr.find("Visor works", browser.screenshot(), exact=False, page=page)
        report(bool(found), f"OCR reads the screen (engine: {ocr._engine})",
               "install ocrmac (macOS) or easyocr, or set VISOR_OCR_ENGINE")
    except Exception as e:
        report(False, "Chromium launches", f"{e}  (try: playwright install chromium)")
    finally:
        browser.close(save=False)

    try:
        import urllib.request
        urllib.request.urlopen(settings.cdp_url.rstrip("/") + "/json/version", timeout=1)
        print(f"  • A Chrome with a debug port is running at {settings.cdp_url}; visor will attach to it")
    except Exception:
        print("  • No Chrome to attach to; visor will launch its own Chromium")
    print("\nAll good." if ok else "\nSome checks failed.")
    return 0 if ok else 1


def main(argv: list = None):
    argv = sys.argv[1:] if argv is None else list(argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        sys.exit(0)

    if argv[0] in COMMANDS:
        command, rest = argv[0], argv[1:]
    elif "--record" in argv:  # legacy: visor --record --flow X --url U --description D
        command, rest = "record", [a for a in argv if a != "--record"]
    else:  # legacy: visor --flow X --targets Y
        command, rest = "run", argv

    handler = {"run": cmd_run, "record": cmd_record, "login": cmd_login,
               "ocr": cmd_ocr, "tree": cmd_tree, "doctor": cmd_doctor}[command]
    sys.exit(handler(rest))

if __name__ == "__main__":
    main()
