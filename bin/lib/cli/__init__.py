import importlib
from pathlib import Path

from .cli import cli

THIS_FILE = Path(__file__)
for file in THIS_FILE.parent.glob("*.py"):
    if file.is_file() and file != THIS_FILE:
        importlib.import_module(f'.{file.stem}', 'lib.cli')
