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
    parser.add_argument("--record",  action="store_true", help="Start recording a new flow")
    parser.add_argument("--url",     type=str, help="Start URL for recording")
    parser.add_argument("--description", type=str, help="Goal description for synthesis")
    args = parser.parse_args()

    if args.record:
        if not args.flow or not args.url or not args.description:
            print("[!] Error: --record requires --flow, --url, and --description")
            sys.exit(1)
            
        print(f"--- Recording New Flow: {args.flow} ---")
        
        from visor.core.recorder import start_recording
        trace_file = start_recording(args.flow, args.url, args.description)
        
        print(f"\n[DAEMON] Recording saved to {trace_file}")
        print(f"[DAEMON] You can now ask your AI Agent to synthesize this flow into a Python script!")
        sys.exit(0)
        
    if not args.flow or not args.targets:
        print("[!] Error: Normal execution requires --flow and --targets")
        sys.exit(1)

    # Load flow dynamically instead of 100 hardcoded branches
    import importlib
    
    # Dynamically load the module based on the flow name
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
