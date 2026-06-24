"""
to_sentences.py

Takes the structured dict produced by parser.py and converts it into
plain English sentences -- the format Hindsight's retain() can read.
"""

import json
import sys


def convert_to_sentences(structure: dict) -> list[str]:
    filepath = structure["filepath"]
    sentences = []

    if structure["imports"]:
        sentences.append(
            f"{filepath} imports the following: {', '.join(structure['imports'])}."
        )

    for fn in structure["functions"]:
        args = ", ".join(fn["args"]) if fn["args"] else "no arguments"
        line = f"{filepath} defines a module-level function named {fn['name']}, which takes {args}."
        if fn["docstring"]:
            line += f" Purpose: {fn['docstring']}"
        sentences.append(line)

    for cls in structure["classes"]:
        class_line = f"{filepath} defines a class named {cls['name']}."
        if cls["docstring"]:
            class_line += f" Purpose: {cls['docstring']}"
        sentences.append(class_line)

        for method in cls["methods"]:
            args = ", ".join(method["args"]) if method["args"] else "no arguments"
            method_line = (
                f"Class {cls['name']} in {filepath} has a method named {method['name']}, "
                f"which takes {args}."
            )
            if method["docstring"]:
                method_line += f" Purpose: {method['docstring']}"
            sentences.append(method_line)

    return sentences


if __name__ == "__main__":
    structure = json.load(sys.stdin)
    for sentence in convert_to_sentences(structure):
        print(sentence)