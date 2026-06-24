"""
parser.py

Walks a single Python file's syntax tree using the built-in `ast` module
and pulls out its structure: imports, functions, and classes (with their
methods).

Usage:
    python parser.py sample.py
"""

import ast
import json
import sys


def parse_python_file(filepath: str) -> dict:
    """
    Parse a single Python file and return its structure as a dict.
    """
    with open(filepath, "r", encoding="utf-8") as f:
        source = f.read()

    tree = ast.parse(source, filename=filepath)

    structure = {
        "filepath": filepath,
        "imports": [],
        "functions": [],
        "classes": [],
    }

    class_method_ids = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            methods = []
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    class_method_ids.add(id(item))
                    methods.append({
                        "name": item.name,
                        "args": [a.arg for a in item.args.args if a.arg != "self"],
                        "docstring": ast.get_docstring(item) or "",
                        "line": item.lineno,
                    })
            structure["classes"].append({
                "name": node.name,
                "docstring": ast.get_docstring(node) or "",
                "line": node.lineno,
                "methods": methods,
            })

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if id(node) in class_method_ids:
                continue
            structure["functions"].append({
                "name": node.name,
                "args": [a.arg for a in node.args.args],
                "docstring": ast.get_docstring(node) or "",
                "line": node.lineno,
            })
        elif isinstance(node, ast.Import):
            for alias in node.names:
                structure["imports"].append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                structure["imports"].append(f"{module}.{alias.name}" if module else alias.name)

    return structure


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python parser.py <path_to_file.py>")
        sys.exit(1)

    result = parse_python_file(sys.argv[1])
    print(json.dumps(result, indent=2))