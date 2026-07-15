"""
retain_upload.py

Ties everything together:
  1. Parses a Python file (parser.py)
  2. Converts the structure to English sentences (to_sentences.py)
  3. Sends those sentences to Hindsight's retain() endpoint for a given bank

Usage:
    python retain_upload.py sample.py

Before running, set these two values below (or pass as env vars):
  HINDSIGHT_URL   - e.g. http://localhost:8888
  BANK_NAME       - e.g. drone-test
"""

import os
import sys
import time
import requests

from parser import parse_python_file
from sentences import convert_to_sentences

HINDSIGHT_URL = os.environ.get("HINDSIGHT_URL", "http://localhost:8888")
BANK_NAME = os.environ.get("BANK_NAME", "drone-test")
POLL_INTERVAL_SECONDS = 5
POLL_TIMEOUT_SECONDS = 300


def retain_sentences(sentences: list[str], document_id: str, source_tag: str = "codebase_structure") -> dict:
    combined_content = "\n".join(sentences)

    url = f"{HINDSIGHT_URL}/v1/default/banks/{BANK_NAME}/memories"
    payload = {
        "items": [
            {
                "content": combined_content,
                "document_id": document_id,
                "context": source_tag,
                "update_mode": "replace",
            }
        ],
        "async": True,
    }

    response = requests.post(url, json=payload, timeout=30)
    response.raise_for_status()
    submission = response.json()

    operation_id = submission.get("operation_id")
    if not operation_id:
        return submission

    print(f"Queued as operation_id={operation_id}. Polling for completion ...")
    return _poll_operation(operation_id)


def _poll_operation(operation_id: str) -> dict:
    url = f"{HINDSIGHT_URL}/v1/default/banks/{BANK_NAME}/operations/{operation_id}"
    waited = 0

    while waited < POLL_TIMEOUT_SECONDS:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        status = response.json()

        state = status.get("status")
        if state in ("completed", "failed"):
            return status

        time.sleep(POLL_INTERVAL_SECONDS)
        waited += POLL_INTERVAL_SECONDS
        print(f"   ... still {state or 'pending'}, waited {waited}s")

    raise TimeoutError(
        f"Operation {operation_id} did not complete within {POLL_TIMEOUT_SECONDS}s. "
        f"Check it manually: GET {url}"
    )


def ingest_file(filepath: str):
    print(f"Parsing {filepath} ...")
    structure = parse_python_file(filepath)

    print("Converting structure to sentences ...")
    sentences = convert_to_sentences(structure)

    if not sentences:
        print("No facts found in this file. Skipping.")
        return

    print(f"Generated {len(sentences)} sentence(s):")
    for s in sentences:
        print(f"   - {s}")

    document_id = filepath

    print(f"\nSending to Hindsight bank '{BANK_NAME}' at {HINDSIGHT_URL} (document_id={document_id}) ...")
    result = retain_sentences(sentences, document_id=document_id)
    print("Done. Final status:")
    print(result)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python retain_upload.py <path_to_file.py>")
        sys.exit(1)

    ingest_file(sys.argv[1])