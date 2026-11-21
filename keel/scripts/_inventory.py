"""Inventory public functions per disconnected module."""
import ast
from pathlib import Path

SRC = Path("src/keel")
mods = [line.strip() for line in Path("scripts/_disconnected.txt").read_text().splitlines()
        if line.strip()] if Path("scripts/_disconnected.txt").exists() else []

for name in mods:
    path = SRC / f"{name}.py"
    if not path.exists():
        continue
    try:
        tree = ast.parse(path.read_text())
    except SyntaxError:
        continue
    funcs = [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
             and not n.name.startswith("_")]
    classes = [n.name for n in tree.body if isinstance(n, ast.ClassDef)
               and not n.name.startswith("_")]
    print(f"{name}: F={','.join(funcs[:6])} C={','.join(classes[:4])}")
