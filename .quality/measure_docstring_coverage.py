"""Measure public API docstring coverage (the real intent of QUALITY-FEEDBACK §8).

radon raw's `comments` only counts `#` lines, NOT docstrings — so the 10%
target is unreachable via docstrings under that metric. This script measures
docstring coverage of public API elements instead, plus docstring-line ratio.
"""
import ast
import pathlib


def public_name(n: str) -> bool:
    return not n.startswith("_")


missing = []
total = 0
covered = 0
doc_lines = 0
code_lines = 0

for p in pathlib.Path("src").rglob("*.py"):
    tree = ast.parse(p.read_text(encoding="utf-8"))
    code_lines += len(p.read_text(encoding="utf-8").splitlines())
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if not public_name(node.name):
                continue
            total += 1
            doc = ast.get_docstring(node)
            if doc:
                covered += 1
                doc_lines += len(doc.splitlines())
            else:
                missing.append(f"{p}:{node.lineno} {node.name}")
        if isinstance(node, ast.ClassDef) and public_name(node.name):
            for m in node.body:
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if not public_name(m.name):
                        continue
                    total += 1
                    doc = ast.get_docstring(m)
                    if doc:
                        covered += 1
                        doc_lines += len(doc.splitlines())
                    else:
                        missing.append(f"{p}:{m.lineno} {node.name}.{m.name}")

print(f"public_api_elements={total} covered={covered} coverage={covered/total:.1%}")
print(f"docstring_lines={doc_lines} code_lines={code_lines} docstring_ratio={doc_lines/code_lines:.1%}")
print(f"MISSING ({len(missing)}):")
for m in missing:
    print("  ", m)
