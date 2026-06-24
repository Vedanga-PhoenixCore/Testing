import os
import sys
import requests

from parser import parse_python_file
from sentences import convert_to_sentences

HINDSIGHT_URL = os.environ.get("HINDSIGHT_URL", "http://localhost:8888")
BANK_NAME = os.environ.get("BANK_NAME", "drone-test")


def retain_sentences(sentences: list[str], document_id: str, source_tag: str = "codebase_structure") -> dict:
    """
    Send sentences to Hindsight's retain endpoint.

    Combines all sentences for one file into a single retain call -- one
    extraction pass per file instead of one per sentence.

    document_id is set to the file's path. This is the upsert key: if you
    re-run this script after editing the file, Hindsight deletes the old
    document and its memories first, then inserts the new ones -- so you
    never accumulate stale duplicate facts for a file that's changed.
    Without document_id, Hindsight assigns a random UUID each call and
    every re-run just piles up more memories for the same file.
    """
    combined_content = "\n".join(sentences)

    # Correct route: /v1/default/banks/{bank_id}/memories
    # Payload shape: {"items": [ {content, document_id, ...}, ... ]}
    url = f"{HINDSIGHT_URL}/v1/default/banks/{BANK_NAME}/memories"
    payload = {
        "items": [
            {
                "content": combined_content,
                "document_id": document_id,
                "context": source_tag,
                "update_mode": "replace",  # explicit: replace old memories for this document_id
            }
        ]
    }

    response = requests.post(url, json=payload, timeout=60)
    response.raise_for_status()
    return response.json()


def ingest_file(filepath: str):
    """Full pipeline for a single file: parse -> sentences -> retain."""
    print(f"Parsing {filepath} ...")
    structure = parse_python_file(filepath)

    print("Converting structure to sentences ...")
    sentences = convert_to_sentences(structure)

    if not sentences:
        print("No facts found in this file (empty or no functions/classes/imports). Skipping.")
        return

    print(f"Generated {len(sentences)} sentence(s):")
    for s in sentences:
        print(f"   - {s}")

    # Use the file path as document_id so re-running this script after an
    # edit upserts (replaces) rather than duplicates the stored memories.
    document_id = filepath

    print(f"\nSending to Hindsight bank '{BANK_NAME}' at {HINDSIGHT_URL} (document_id={document_id}) ...")
    result = retain_sentences(sentences, document_id=document_id)
    print("Done. Response from Hindsight:")
    print(result)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python retain_upload.py <path_to_file.py>")
        sys.exit(1)

    ingest_file(sys.argv[1])