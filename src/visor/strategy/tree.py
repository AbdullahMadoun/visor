import json
import os

from visor.core import WORKSPACE_DIR

DEFAULT_TREE_PATH = os.path.join(os.path.dirname(__file__), "tree.json")
TREE_PATH = os.environ.get("VISOR_STRATEGY_TREE", os.path.join(WORKSPACE_DIR, "tree.json"))

def load() -> dict:
    if os.path.exists(TREE_PATH):
        with open(TREE_PATH) as f:
            return json.load(f)
    if os.path.exists(DEFAULT_TREE_PATH):
        with open(DEFAULT_TREE_PATH) as f:
            return json.load(f)
    return {}

def save(tree: dict):
    os.makedirs(os.path.dirname(TREE_PATH), exist_ok=True)
    with open(TREE_PATH, "w") as f:
        json.dump(tree, f, indent=2)

# Files kept next to tree.json: fixes that failed (shown to the agent) and, in review mode,
# proven fixes waiting for a person to approve them
REJECTED = "rejected.json"
PENDING = "pending.json"
MAX_REJECTED = 50


def side_path(name: str) -> str:
    return os.path.join(os.path.dirname(TREE_PATH) or ".", name)


def load_side(name: str) -> list:
    try:
        with open(side_path(name)) as f:
            items = json.load(f)
        return items if isinstance(items, list) else []
    except (OSError, ValueError):
        return []


def save_side(name: str, items: list):
    path = side_path(name)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def add_rejected(entry: dict):
    save_side(REJECTED, (load_side(REJECTED) + [entry])[-MAX_REJECTED:])


def review(ask=input) -> int:
    """
    Go through proven fixes waiting in pending.json: approve (write to the tree), reject
    (drop, and tell the agent next time) or leave for later. Returns how many are left.
    """
    pending = load_side(PENDING)
    if not pending:
        print("[TREE] Nothing waiting for review.")
        return 0
    left = []
    for n, item in enumerate(pending, 1):
        keys, branch = item["branch"].split("."), item["fix"]
        print(f"\n({n}/{len(pending)}) {item['branch']}")
        print(json.dumps(branch, indent=2, ensure_ascii=False))
        answer = (ask("[a]pprove, [r]eject, or Enter to decide later: ") or "").strip().lower()
        if answer.startswith("a"):
            set_branch(load(), keys, branch)
        elif answer.startswith("r"):
            add_rejected({"branch": item["branch"], "fix": branch, "why": "rejected by a reviewer"})
            print(f"[TREE] Rejected {item['branch']}")
        else:
            left.append(item)
    save_side(PENDING, left)
    print(f"\n[TREE] {len(pending) - len(left)} decided, {len(left)} left for later.")
    return len(left)


def get(tree: dict, *keys):
    """Navigate nested keys, return None if path doesn't exist."""
    node = tree
    for k in keys:
        if not isinstance(node, dict) or k not in node:
            return None
        node = node[k]
    return node

def set_branch(tree: dict, keys: list, value: dict):
    """Set a nested key path in the tree."""
    node = tree
    for k in keys[:-1]:
        node = node.setdefault(k, {})
    node[keys[-1]] = value
    save(tree)
    print(f"[TREE] Updated branch: {' > '.join(keys)}")

def show_map():
    """Prints a beautiful live map of the current Strategy Tree."""
    try:
        from rich.tree import Tree
        from rich import print as rprint
    except ImportError:
        print("[!] Install 'rich' to see the live map: pip install rich")
        return

    data = load()
    if not data:
        print("[TREE] Strategy tree is currently empty.")
        return

    def build_tree(d, p_node):
        for k, v in d.items():
            if isinstance(v, dict):
                # If it has "action", it's a leaf node instruction
                if "action" in v:
                    action_str = f"[bold green]action:[/bold green] {v['action']}"
                    if "target" in v:
                        action_str += f" [cyan]target:[/cyan] {v['target']}"
                    if "reason" in v:
                        action_str += f" [yellow]reason:[/yellow] {v['reason']}"
                    
                    child = p_node.add(f"[bold magenta]{k}[/bold magenta] → {action_str}")
                else:
                    # It's an intermediate branch
                    child = p_node.add(f"[bold cyan]{k}[/bold cyan]")
                    build_tree(v, child)

    root = Tree("🧠 [bold blue]Visor Strategy Tree (Live Map)[/bold blue]")
    build_tree(data, root)
    rprint(root)
    print("\n")

if __name__ == "__main__":
    show_map()
