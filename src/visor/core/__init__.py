import os
import pathlib

# Resolve project root dynamically
PROJECT_ROOT = str(pathlib.Path(__file__).parent.parent.parent.parent.resolve())
# Workspace dir defaults to ./visor_workspace in current working directory, or VISOR_WORKSPACE env var
WORKSPACE_DIR = os.environ.get(
    "VISOR_WORKSPACE",
    os.path.join(os.getcwd(), "visor_workspace")
)