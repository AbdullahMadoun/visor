"""
visor entry point.

Usage:
  python run.py --flow my_custom_flow --targets targets.csv
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

from visor.core.runner import run_flow
from visor.core import PROJECT_ROOT

def load_targets(path: str) -> list[str]:
    targets = []
    with open(path) as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        target_col = "target" if "target" in fieldnames else ("url" if "url" in fieldnames else (fieldnames[0] if fieldnames else "target"))
        for row in reader:
            val = row.get(target_col, "").strip()
            status = row.get("status", "pending").strip()
            # Exclude any success or any skipped variant (skipped:reason)
            if val and status != "success" and not status.startswith("skipped"):
                targets.append(val)
    return targets

def main():
    parser = argparse.ArgumentParser(description="visor — self-healing browser automation")
    parser.add_argument("--flow",    required=False, help="Flow to run (e.g. my_custom_flow)")
    parser.add_argument("--targets", required=False, help="CSV file with 'url' column")
    parser.add_argument("--retries", type=int, default=1, help="Max retry loops until 100%% success")
    parser.add_argument("--record",  required=False, help="Launch the semantic UI overlay recorder to record a new flow")
    parser.add_argument("--url",     required=False, help="Starting URL for recording mode")
    args = parser.parse_args()

    if args.record:
        if not args.url:
            print("[!] Error: --url is required when using --record")
            sys.exit(1)
        from visor.core.recorder import start_recording
        start_recording(args.record, args.url, "User-recorded workflow")
        from visor.core import browser
        browser.close()
        print(f"\n[DAEMON] Recording complete. You can now ask the agent to synthesize '{args.record}'.")
        sys.exit(0)

    if not args.flow or not args.targets:
        print("[!] Error: --flow and --targets are required for running a workflow")
        sys.exit(1)

    # Load flow dynamically instead of 100 hardcoded branches
    import importlib
    
    if args.flow.startswith("mind2web_task_"):
        module_name = f"visor.platforms.mind2web.{args.flow.replace('mind2web_', '')}"
    elif args.flow.startswith("benchmark_task_"):
        module_name = f"visor.platforms.benchmark.{args.flow.replace('benchmark_', '')}"
    else:
        if "_" in args.flow:
            platform, flow_name = args.flow.split("_", 1)
            module_name = f"visor.platforms.{platform}.{flow_name}"
        else:
            module_name = f"visor.platforms.{args.flow}.main"
            
    try:
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
            flow_fn_name = args.flow.split("_", 1)[1] if "_" in args.flow else args.flow
            last_segment = args.flow.split("_")[-1]
            flow_fn = getattr(module, flow_fn_name, getattr(module, last_segment, None))
        
        if not callable(flow_fn):
            raise AttributeError(f"Could not find callable entry point in {module_name}")
            
    except Exception as e:
        print(f"[ERROR] Failed to dynamically load flow '{args.flow}': {e}")
        sys.exit(1)

    targets = load_targets(args.targets)
    print(f"[visor] Flow: {args.flow} | Targets: {len(targets)} | Max retries: {args.retries}")
    
    # Show the live map of what the bot currently knows
    from visor.strategy import tree
    tree.show_map()

    results_csv = os.path.join(PROJECT_ROOT, "visor_workspace", "logs", "results.csv")
    run_flow(flow_fn, targets, results_csv, max_retries=args.retries)
    
    # Clean up browser session
    from visor.core import browser
    browser.close()

    print("\n[DAEMON] Task complete.")

if __name__ == "__main__":
    main()
