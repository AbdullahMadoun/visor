import json
import os

TREE_PATH = os.path.join(os.path.dirname(__file__), "tree.json")

def load() -> dict:
    if os.path.exists(TREE_PATH):
        with open(TREE_PATH) as f:
            return json.load(f)
    return {}

def save(tree: dict):
    with open(TREE_PATH, "w") as f:
        json.dump(tree, f, indent=2)

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
