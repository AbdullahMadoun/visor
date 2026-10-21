import os
import pathlib

# Resolve project root dynamically
PROJECT_ROOT = str(pathlib.Path(__file__).parent.parent.parent.parent.resolve())


def _resolve_workspace_dir() -> str:
    # Explicit override wins
    if os.environ.get("VISOR_WORKSPACE"):
        return os.environ["VISOR_WORKSPACE"]
    # Keep using an existing repo-level workspace (saved session, learned tree) wherever visor is run from
    legacy = os.path.join(PROJECT_ROOT, "visor_workspace")
    if os.path.isdir(legacy):
        return legacy
    return os.path.join(os.getcwd(), "visor_workspace")


WORKSPACE_DIR = _resolve_workspace_dir()
