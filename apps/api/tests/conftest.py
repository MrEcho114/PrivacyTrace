from copy import deepcopy
from hashlib import sha256

import pytest

from privacytrace.resources import read_json


@pytest.fixture(autouse=True)
def private_scan_run_root(tmp_path, monkeypatch):
    # Public runtime configuration, never the user's historical scan cache.
    monkeypatch.setenv("PRIVACYTRACE_APK_RUN_ROOT", str(tmp_path / "apk-runs"))


@pytest.fixture
def bundle_data():
    data = deepcopy(read_json("samples/demo/evaluation-input.json"))
    data["behaviors"] = [data["behaviors"][0]]
    data["policy_documents"] = [data["policy_documents"][0]]
    doc = data["policy_documents"][0]
    text = "我们访问精确位置。我们访问位置信息。我们可能访问相关信息。"
    doc["artifact"]["text"] = text
    doc["artifact"]["sha256"] = sha256(text.encode()).hexdigest()
    data["evidence"] = [
        item
        for item in data["evidence"]
        if not item.get("document_id") or item["document_id"] == doc["id"]
    ]
    snapshot = next(item for item in data["evidence"] if item["id"] == doc["evidence_id"])
    snapshot["artifact_sha256"] = doc["artifact"]["sha256"]
    sentence = next(item for item in data["evidence"] if item["kind"] == "POLICY_SENTENCE")
    sentence["excerpt"] = "我们访问精确位置。"
    sentence.update(start_offset=0, end_offset=9)
    data["policy_claims"] = [
        {
            "id": "claim-precise-location",
            "document_id": doc["id"],
            "data_type": "PRECISE_LOCATION",
            "action": "ACCESS",
            "polarity": "AFFIRMATIVE",
            "subject": "HOST_APP",
            "evidence_ids": [sentence["id"]],
        }
    ]
    return data
