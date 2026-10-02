"""Read-only demo and validated pure-rule evaluation API; no APK intake yet."""

from fastapi import FastAPI, HTTPException

from .consistency import evaluate
from .models import EvaluationInput, EvaluationResult
from .resources import read_json, taxonomy

app = FastAPI(title="PrivacyTrace", version="0.1.0")


@app.get("/api/v1/health")
def health():
    return {"status": "ok", "version": "0.1.0", "mode": "scaffold"}


@app.get("/api/v1/taxonomy")
def get_taxonomy():
    return taxonomy()


@app.get("/api/v1/demo/report")
def demo_report():
    bundle = EvaluationInput.model_validate(read_json("samples/demo/evaluation-input.json"))
    return {
        "demo": True,
        "sample": {
            "name": "PrivacyTrace 示例 App",
            "package_name": "org.privacytrace.demo",
            "version": "synthetic-0.1",
            "input_mode": "SYNTHETIC",
        },
        "job": bundle.job,
        "result": evaluate(bundle),
        "evidence": bundle.evidence,
        "behaviors": bundle.behaviors,
        "policy_documents": bundle.policy_documents,
    }


@app.get("/api/v1/demo/evidence/{evidence_id}")
def demo_evidence(evidence_id: str):
    bundle = EvaluationInput.model_validate(read_json("samples/demo/evaluation-input.json"))
    for item in bundle.evidence:
        if item.id == evidence_id:
            return item
    raise HTTPException(status_code=404, detail="Evidence not found")


@app.post("/api/v1/consistency/evaluate", response_model=EvaluationResult)
def evaluate_evidence(bundle: EvaluationInput):
    return evaluate(bundle)
