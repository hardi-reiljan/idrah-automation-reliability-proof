from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / "workflow" / "reliability-sandbox-v0.1.json"

def load_workflow() -> dict:
    return json.loads(WORKFLOW.read_text(encoding="utf-8"))

def test_workflow_is_inactive_and_has_no_n8n_credentials_block() -> None:
    workflow = load_workflow()
    raw = WORKFLOW.read_text(encoding="utf-8").lower()
    assert workflow["active"] is False
    assert chr(34) + "credentials" + chr(34) not in raw

def test_idempotency_is_committed_only_after_success() -> None:
    workflow = load_workflow()
    outputs = workflow["connections"]["Downstream Succeeded?"]["main"]
    assert outputs[0] == [{"node": "Commit Idempotency Key", "type": "main", "index": 0}]
    assert outputs[1] == [{"node": "Build Failure Response", "type": "main", "index": 0}]
