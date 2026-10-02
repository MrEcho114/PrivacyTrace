"""Initial rules evaluate data-type disclosure only, never actual collection or legality."""

from .models import (
    EvaluationInput,
    EvaluationResult,
    MatchStatus,
    PolicyDocument,
    PolicySource,
    PrivacyBehavior,
    PrivacyIssue,
)
from .resources import taxonomy

SOURCE_LABELS = {
    PolicySource.IN_APP_POLICY: "App 内政策",
    PolicySource.STORE_POLICY: "应用商店声明",
    PolicySource.OFFICIAL_WEB_POLICY: "官网政策",
    PolicySource.SDK_POLICY: "SDK 自有政策",
}


def evaluate(bundle: EvaluationInput) -> EvaluationResult:
    rules = taxonomy()
    types = {item["id"]: item for item in rules["data_types"]}
    evidence = {item.id: item for item in bundle.evidence}
    issues: list[PrivacyIssue] = []

    def ancestors(data_type: str) -> set[str]:
        result: set[str] = set()
        parent = types[data_type].get("parent")
        while parent:
            result.add(parent)
            parent = types[parent].get("parent")
        return result

    def add(
        behavior: PrivacyBehavior,
        status: MatchStatus,
        docs: list[PolicyDocument],
        refs: list[str],
        explanation: str,
    ) -> PrivacyIssue:
        issue = PrivacyIssue(
            id=f"issue-{len(issues) + 1}",
            behavior_id=behavior.id,
            data_type=behavior.data_type,
            status=status,
            policy_document_ids=[doc.id for doc in docs],
            evidence_ids=list(dict.fromkeys(behavior.evidence_ids + refs)),
            explanation=explanation,
        )
        issues.append(issue)
        return issue

    for behavior in bundle.behaviors:
        label = types[behavior.data_type]["label"]
        has_api = behavior.action == "ACCESS" and any(
            evidence[ref].kind == "API" for ref in behavior.evidence_ids
        )
        # SDK policies cannot substitute for a host app's disclosure.
        host_docs = [
            doc for doc in bundle.policy_documents if doc.source_type != PolicySource.SDK_POLICY
        ]
        if not has_api or not host_docs:
            add(
                behavior,
                MatchStatus.INSUFFICIENT_EVIDENCE,
                [],
                [],
                f"关于{label}，当前缺少可核验的 API 访问证据或宿主政策，证据不足。",
            )
            continue
        per_source: list[tuple[PolicyDocument, PrivacyIssue]] = []
        for doc in host_docs:
            candidates = [
                claim
                for claim in bundle.policy_claims
                if claim.document_id == doc.id
                and (
                    claim.data_type == behavior.data_type
                    or claim.data_type in ancestors(behavior.data_type)
                )
            ]
            clear = [
                claim
                for claim in candidates
                if not claim.ambiguity_flags and claim.action == "ACCESS"
            ]
            exact = [claim for claim in clear if claim.data_type == behavior.data_type]
            refs = [doc.evidence_id]
            if exact:
                status = MatchStatus.EXACT_MATCH
                chosen = exact
                tail = "明确提到了这一数据类型；目的、接收方和实际运行情况仍需分别核验。"
            elif clear:
                status = MatchStatus.CATEGORY_MATCH
                chosen = clear
                tail = "只提到了上位类别，没有明确说明这一具体数据类型。"
            elif candidates:
                status = MatchStatus.AMBIGUOUS_DISCLOSURE
                chosen = candidates
                tail = "有相关表述，但措辞或行为描述不够清楚。"
            elif doc.completeness == "PARTIAL":
                status = MatchStatus.INSUFFICIENT_EVIDENCE
                chosen = []
                tail = "快照不完整，不能据此判断是否声明了这一数据类型。"
            else:
                status = MatchStatus.NOT_DECLARED
                chosen = []
                tail = "在当前人工整理的结构化声明中没有对应条目，需复核完整政策原文。"
            for claim in chosen:
                refs.extend(claim.evidence_ids)
            issue = add(
                behavior,
                status,
                [doc],
                refs,
                f"检测到代码中存在访问{label}的 API 证据。{SOURCE_LABELS[doc.source_type]}{tail}",
            )
            per_source.append((doc, issue))
        positive = {MatchStatus.EXACT_MATCH, MatchStatus.CATEGORY_MATCH}
        # Compare distinct host channels. Absence in partial documents is never a conflict.
        conflicting = [
            (d, i)
            for d, i in per_source
            if i.status in positive or i.status == MatchStatus.NOT_DECLARED
        ]
        has_conflict = any(
            d1.source_type != d2.source_type
            and (
                (i1.status in positive and i2.status == MatchStatus.NOT_DECLARED)
                or (i2.status in positive and i1.status == MatchStatus.NOT_DECLARED)
            )
            for d1, i1 in conflicting
            for d2, i2 in conflicting
        )
        if has_conflict:
            add(
                behavior,
                MatchStatus.POLICY_SOURCE_CONFLICT,
                [d for d, _ in conflicting],
                [ref for _, i in conflicting for ref in i.evidence_ids],
                f"关于{label}，宿主 App 在不同渠道的结构化声明存在差异，"
                "请复核政策原文、适用版本和采集时间。",
            )
    return EvaluationResult(job_id=bundle.job.id, ruleset_version=rules["version"], issues=issues)
