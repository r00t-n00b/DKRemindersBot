import ast
from pathlib import Path


def test_main_has_no_duplicate_top_level_function_names():
    source = Path("main.py").read_text()
    tree = ast.parse(source)

    names = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.append(node.name)

    duplicates = sorted({name for name in names if names.count(name) > 1})

    assert duplicates == []
