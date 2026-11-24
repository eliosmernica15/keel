"""Real AST-based codemods (C4.4 upgrade).

Structural rewrites of Python source with a unified-diff preview before any
file is changed. Transformations are conservative and verified by re-parsing.
"""

from __future__ import annotations

import ast
import difflib
from pathlib import Path


def rename_symbol(source: str, old: str, new: str) -> str:
    """Rename all Name/attribute references of a symbol via AST."""
    tree = ast.parse(source)

    class Renamer(ast.NodeTransformer):
        def visit_Name(self, node):
            if node.id == old:
                node.id = new
            return node

        def visit_Attribute(self, node):
            # Attribute references (``obj.old`` / ``self.old``) are symbol
            # references too; without this, a rename silently leaves the
            # majority of real-world call sites untouched.
            if node.attr == old:
                node.attr = new
            return self.generic_visit(node)

        def visit_FunctionDef(self, node):
            if node.name == old:
                node.name = new
            return self.generic_visit(node)

        def visit_ClassDef(self, node):
            if node.name == old:
                node.name = new
            return self.generic_visit(node)

    rewritten = Renamer().visit(tree)
    ast.fix_missing_locations(rewritten)
    return ast.unparse(rewritten) + "\n"


def replace_call(source: str, old_call: str, new_call: str) -> str:
    """Replace calls named ``old_call`` with ``new_call`` via AST."""
    tree = ast.parse(source)

    class Replacer(ast.NodeTransformer):
        def visit_Call(self, node):
            name = None
            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                name = node.func.attr
            if name == old_call:
                node.func = ast.Name(id=new_call, ctx=ast.Load())
            return self.generic_visit(node)

    rewritten = Replacer().visit(tree)
    ast.fix_missing_locations(rewritten)
    return ast.unparse(rewritten) + "\n"


def preview(path: str | Path, transform) -> dict:
    """Return a unified diff for a transform without writing the file."""
    source = Path(path).read_text(encoding="utf-8")
    result = transform(source)
    ast.parse(result)  # verify the rewrite is valid Python
    diff = difflib.unified_diff(
        source.splitlines(), result.splitlines(),
        fromfile=str(path), tofile=str(path) + " (rewritten)", lineterm="")
    return {"changed": source != result, "diff": "\n".join(diff)}


def apply(path: str | Path, transform) -> dict:
    """Apply a verified transform to a file."""
    result = preview(path, transform)
    if result["changed"]:
        Path(path).write_text(
            transform(Path(path).read_text(encoding="utf-8")), encoding="utf-8")
    return result
