"""Generate the shared contract from the authoritative Python models."""

import json
from pathlib import Path

from privacytrace.models import EvaluationInput, EvaluationResult

target = Path(__file__).resolve().parents[1] / "packages" / "contracts"
target.mkdir(parents=True, exist_ok=True)
for name, model in [("evaluation-input", EvaluationInput), ("evaluation-result", EvaluationResult)]:
    (target / f"{name}.schema.json").write_text(
        json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
print("Updated input and result JSON Schemas")
