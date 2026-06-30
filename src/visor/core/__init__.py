import pathlib

# Resolve project root dynamically (visor/src/visor/core/__init__.py -> 3 parents up is src, 4 is visor/)
PROJECT_ROOT = str(pathlib.Path(__file__).parent.parent.parent.parent.resolve())