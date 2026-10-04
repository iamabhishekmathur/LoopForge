"""Readable HTML reports for trace-level judge evaluation."""

from __future__ import annotations

from datetime import datetime
from html import escape
import json
from pathlib import Path
from typing import Any


GROUPS = (
    ("clear_issue", "Clear issues"),
    ("likely_issue", "Likely issues"),
    ("acceptable_behavior", "Acceptable"),
    ("insufficient_evidence", "Needs evidence"),
    ("failed", "Failed"),
)


def write_judge_evaluation_html(report: dict[str, Any], json_path: Path) -> Path:
    path = json_path.with_suffix(".html")
    path.write_text(judge_evaluation_html(report), encoding="utf-8")
    return path


def judge_evaluation_html(report: dict[str, Any]) -> str:
    records = list(report.get("records") or [])
    counts = {key: 0 for key, _ in GROUPS}
    for record in records:
        counts[_classification(record)] = counts.get(_classification(record), 0) + 1
    groups = "".join(
        _group(key, label, [record for record in records if _classification(record) == key])
        for key, label in GROUPS
    )
    generated_at = _text(report.get("generated_at"))
    provider = _text(report.get("probabilistic_provider") or "not configured")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LoopForge trace evaluation</title>
<style>
:root{{--ink:#17202a;--muted:#68717d;--line:#dfe3e8;--soft:#f6f7f8;--red:#b42318;--amber:#9a6700;--green:#18794e;--blue:#175cd3}}
*{{box-sizing:border-box}} body{{margin:0;background:#fff;color:var(--ink);font:14px/1.48 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;letter-spacing:0}}
main{{max-width:1180px;margin:0 auto;padding:32px 24px 64px}} h1{{font-size:28px;margin:0 0 6px}} h2{{font-size:20px;margin:36px 0 12px}} h3{{font-size:17px;margin:0}} p{{margin:0}} code{{font:12px ui-monospace,SFMono-Regular,Menlo,monospace}}
.sub{{color:var(--muted)}} .summary{{display:grid;grid-template-columns:repeat(5,minmax(110px,1fr));border:1px solid var(--line);margin:22px 0 12px}}
.metric{{padding:14px 16px;border-right:1px solid var(--line)}} .metric:last-child{{border:0}} .metric b{{display:block;font-size:21px}} .metric span{{color:var(--muted);font-size:12px}}
.tabs{{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0}} button{{border:1px solid var(--line);background:#fff;padding:7px 11px;cursor:pointer;font-weight:600}} button.active{{background:var(--ink);color:#fff;border-color:var(--ink)}}
.case{{border:1px solid var(--line);border-left:4px solid var(--blue);margin:12px 0;background:#fff}} .case.clear_issue{{border-left-color:var(--red)}} .case.likely_issue{{border-left-color:var(--amber)}} .case.acceptable_behavior{{border-left-color:var(--green)}} .case.insufficient_evidence,.case.failed{{border-left-color:#77808c}}
.case-head{{display:flex;justify-content:space-between;gap:16px;padding:15px 18px;border-bottom:1px solid var(--line)}} .case-meta{{color:var(--muted);font-size:12px;margin-top:4px}} .badges{{display:flex;align-items:flex-start;gap:6px;flex-wrap:wrap;justify-content:flex-end}}
.badge{{font-size:11px;font-weight:700;padding:3px 7px;border:1px solid var(--line);text-transform:uppercase}} .badge.strong{{color:var(--green);border-color:#a9d8c2}} .badge.weak,.badge.insufficient{{color:var(--red);border-color:#efb4ae}} .badge.moderate{{color:var(--amber);border-color:#e7cc8b}}
.qa{{display:grid;grid-template-columns:1fr 1fr;gap:0;border-bottom:1px solid var(--line)}} .qa>section{{padding:16px 18px;min-width:0}} .qa>section+section{{border-left:1px solid var(--line)}} .label{{display:block;color:var(--muted);font-size:11px;font-weight:700;text-transform:uppercase;margin-bottom:7px}} .content{{white-space:pre-wrap;overflow-wrap:anywhere}}
.finding{{padding:16px 18px;border-bottom:1px solid var(--line)}} .finding-grid{{display:grid;grid-template-columns:1fr 1fr;gap:28px}} .issue-text{{font-size:16px;font-weight:650}} .why{{color:var(--muted);margin-top:5px}} .recommendation{{font-weight:600}}
.evals{{width:100%;border-collapse:collapse}} .evals th,.evals td{{text-align:left;padding:9px 12px;border-top:1px solid var(--line);vertical-align:top}} .evals th{{color:var(--muted);font-size:11px;text-transform:uppercase;background:var(--soft)}} .evals td:first-child{{font-weight:600}} .label-issue{{color:var(--red);font-weight:700}} .label-pass{{color:var(--green);font-weight:700}} .label-uncertain{{color:var(--amber);font-weight:700}}
.meter{{width:90px;height:5px;background:#e8eaed;margin-top:5px}} .meter i{{display:block;height:100%;background:var(--blue)}} details{{border-top:1px solid var(--line)}} summary{{padding:12px 18px;cursor:pointer;font-weight:650}} .detail-body{{padding:4px 18px 18px}}
.support{{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:16px}} .support div{{background:var(--soft);padding:9px 10px}} .support b{{display:block}} .support span{{color:var(--muted);font-size:11px}}
.timeline{{position:relative;margin:10px 0 0 10px;padding-left:22px;border-left:2px solid #ccd3db}} .step{{position:relative;padding:0 0 16px}} .step:before{{content:"";position:absolute;left:-29px;top:3px;width:12px;height:12px;border:2px solid #8792a2;background:#fff;border-radius:50%}} .step.issue:before{{border-color:var(--red);background:#fff0ee}} .step.error:before{{border-color:var(--red);background:var(--red)}} .step-title{{font-weight:650}} .step-meta{{color:var(--muted);font-size:11px}} .step pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:var(--soft);padding:8px;margin:6px 0 0;max-height:180px;overflow:auto;font:11px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace}}
.empty{{padding:18px;color:var(--muted);border:1px dashed var(--line)}} .raw{{white-space:pre-wrap;overflow-wrap:anywhere;background:var(--soft);padding:12px;max-height:400px;overflow:auto;font:11px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace}}
@media(max-width:760px){{main{{padding:20px 12px}}.summary{{grid-template-columns:repeat(2,1fr)}}.qa,.finding-grid{{grid-template-columns:1fr}}.qa>section+section{{border-left:0;border-top:1px solid var(--line)}}.support{{grid-template-columns:repeat(2,1fr)}}.evals th:nth-child(4),.evals td:nth-child(4){{display:none}}}}
</style>
</head>
<body><main>
<h1>Trace evaluation</h1>
<p class="sub">{escape(str(len(records)))} traces &middot; probabilistic provider: {escape(provider)} &middot; generated {escape(generated_at)}</p>
<div class="summary">{''.join(_summary_metric(counts[key], label) for key, label in GROUPS)}</div>
<div class="tabs"><button class="active" data-filter="all">All</button>{''.join(f'<button data-filter="{key}">{escape(label)} ({counts[key]})</button>' for key,label in GROUPS)}</div>
{groups}
</main>
<script>
document.querySelectorAll('[data-filter]').forEach(button=>button.addEventListener('click',()=>{{
 document.querySelectorAll('[data-filter]').forEach(x=>x.classList.remove('active')); button.classList.add('active');
 const filter=button.dataset.filter; document.querySelectorAll('.report-group').forEach(group=>{{group.style.display=filter==='all'||group.dataset.group===filter?'block':'none'}});
}}));
</script></body></html>"""


def _summary_metric(value: int, label: str) -> str:
    return f'<div class="metric"><b>{value}</b><span>{escape(label)}</span></div>'


def _group(key: str, label: str, records: list[dict[str, Any]]) -> str:
    cards = "".join(_case(record, key) for record in records)
    if not cards:
        cards = '<div class="empty">No traces in this group.</div>'
    return f'<section class="report-group" data-group="{key}"><h2>{escape(label)} <span class="sub">{len(records)}</span></h2>{cards}</section>'


def _case(record: dict[str, Any], classification: str) -> str:
    resolved = record.get("calibrated_trace_resolution") or {}
    audit = record.get("audit") or {}
    reference = audit.get("reference_assessment") or {}
    decision = record.get("calibrated_decision") or {}
    finding = _primary_finding(decision)
    evaluator_result = record.get("probabilistic_evaluation") or {}
    support = record.get("decision_support") or {}
    explicit_query = bool(resolved.get("current_turn_request"))
    query = resolved.get("current_turn_request") or record.get("user_intent") or "Not resolved"
    query_label = "User query" if explicit_query else "Inferred intent"
    response = resolved.get("resolved_terminal_outcome") or record.get("final_response") or "Not resolved"
    core_issue = (
        reference.get("core_issue")
        or finding.get("title")
        or ("No material issue identified." if classification == "acceptable_behavior" else reference.get("rationale"))
        or "The available evidence was not sufficient for a stable decision."
    )
    why = reference.get("why_it_matters") or finding.get("hypothesis") or reference.get("rationale") or ""
    recommendation = (
        reference.get("recommended_action")
        or finding.get("recommended_next_action")
        or _evaluator_recommendation(evaluator_result)
        or ("No harness change recommended." if classification == "acceptable_behavior" else "Collect the missing evidence and rerun the evaluators.")
    )
    trace_id = _text(record.get("trace_id"))
    support_label = _text(support.get("support") or "insufficient")
    badges = [
        f'<span class="badge">{escape(classification.replace("_", " "))}</span>',
        f'<span class="badge {escape(support_label)}">{escape(support_label)} support</span>',
    ]
    if support.get("requires_escalation"):
        badges.append('<span class="badge weak">escalated</span>')
    if not explicit_query:
        badges.append('<span class="badge weak">request inferred</span>')
    return f"""<article class="case {classification}">
<header class="case-head"><div><h3>{escape(_short(core_issue, 120))}</h3><div class="case-meta"><code>{escape(trace_id)}</code> &middot; {record.get('span_count', 0)} spans</div></div><div class="badges">{''.join(badges)}</div></header>
<div class="qa"><section><span class="label">{query_label}</span><div class="content">{escape(_short(query, 1800))}</div></section><section><span class="label">Final agent response</span><div class="content">{escape(_short(response, 2400))}</div></section></div>
<section class="finding"><div class="finding-grid"><div><span class="label">Core issue</span><div class="issue-text">{escape(_short(core_issue, 420))}</div><div class="why">{escape(_short(why, 520))}</div></div><div><span class="label">Recommended change</span><div class="recommendation">{escape(_short(recommendation, 520))}</div></div></div></section>
{_evaluator_table(evaluator_result)}
<details><summary>Decision verification</summary><div class="detail-body">{_support(support)}</div></details>
<details><summary>Trace timeline</summary><div class="detail-body">{_timeline(record)}</div></details>
<details><summary>Judge details</summary><div class="detail-body"><pre class="raw">{escape(json.dumps(_compact_judge_details(audit, decision), indent=2, sort_keys=True))}</pre></div></details>
</article>"""


def _evaluator_table(result: dict[str, Any]) -> str:
    rows = []
    for item in result.get("evaluators") or []:
        label = _text(item.get("label") or "uncertain")
        confidence = float(item.get("confidence") or 0)
        rationale = item.get("issue") or item.get("rationale") or ""
        rows.append(
            f'<tr><td>{escape(_text(item.get("name")))}</td><td class="label-{escape(label)}">{escape(label.replace("_", " "))}</td>'
            f'<td>{confidence:.0%}<div class="meter"><i style="width:{confidence:.0%}"></i></div></td><td>{escape(_short(rationale, 260))}</td></tr>'
        )
    if not rows:
        return '<div class="finding"><span class="label">Evaluators</span><div class="sub">No probabilistic evaluator result.</div></div>'
    return '<table class="evals"><thead><tr><th>Evaluator</th><th>Verdict</th><th>Model confidence</th><th>Basis</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table>"


def _support(support: dict[str, Any]) -> str:
    metrics = (
        ("Evaluator confidence", _percent(support.get("evaluator_confidence"))),
        ("Judge agreement", "Yes" if support.get("judge_agreement") else "No"),
        ("Evidence coverage", _percent(support.get("evidence_coverage"))),
        ("Decision stability", _percent(support.get("decision_stability"))),
        ("Verification pass rate", _percent(support.get("challenge_pass_rate"))),
    )
    blocks = "".join(f'<div><b>{escape(value)}</b><span>{escape(label)}</span></div>' for label, value in metrics)
    checks = "".join(
        f'<li>{"Pass" if item.get("passed") else "Review"}: {escape(_text(item.get("check")).replace("_", " "))}</li>'
        for item in support.get("checks") or []
    )
    return f'<div class="support">{blocks}</div><ul>{checks}</ul><p class="sub">{escape(_text(support.get("semantics")))}</p>'


def _timeline(record: dict[str, Any]) -> str:
    issue_refs = {
        str(ref)
        for evaluator in (record.get("probabilistic_evaluation") or {}).get("evaluators") or []
        if evaluator.get("label") == "issue"
        for ref in evaluator.get("evidence_ids") or []
    }
    steps = []
    for index, item in enumerate(record.get("trace_timeline") or []):
        step_id = _text(item.get("step_id"))
        classes = ["step"]
        if item.get("error"):
            classes.append("error")
        if any(step_id in ref or _text(item.get("name")) in ref for ref in issue_refs):
            classes.append("issue")
        duration = _duration(item.get("started_at"), item.get("ended_at"))
        previews = []
        if item.get("input_preview"):
            previews.append("Input\n" + _short(item.get("input_preview"), 500))
        if item.get("output_preview"):
            previews.append("Output\n" + _short(item.get("output_preview"), 500))
        if item.get("error"):
            previews.append("Error\n" + _short(item.get("error"), 500))
        detail = f'<pre>{escape(chr(10).join(previews))}</pre>' if previews else ""
        steps.append(
            f'<div class="{" ".join(classes)}"><div class="step-title">{index + 1}. {escape(_text(item.get("name")))}</div>'
            f'<div class="step-meta">{escape(_text(item.get("step_type")))} &middot; {escape(duration)} &middot; <code>{escape(step_id)}</code></div>{detail}</div>'
        )
    return '<div class="timeline">' + "".join(steps) + "</div>" if steps else '<p class="sub">No timeline was captured.</p>'


def _classification(record: dict[str, Any]) -> str:
    if record.get("status") != "complete":
        return "failed"
    value = _text(((record.get("audit") or {}).get("reference_assessment") or {}).get("classification"))
    return value if value in {key for key, _ in GROUPS} else "insufficient_evidence"


def _primary_finding(decision: dict[str, Any]) -> dict[str, Any]:
    findings = [item for item in decision.get("findings") or [] if isinstance(item, dict)]
    unresolved = [item for item in findings if item.get("resolution_state") != "resolved_in_trace"]
    return (unresolved or findings or [{}])[0]


def _evaluator_recommendation(result: dict[str, Any]) -> str | None:
    for item in result.get("evaluators") or []:
        if item.get("label") == "issue" and item.get("recommendation"):
            return _text(item.get("recommendation"))
    return None


def _compact_judge_details(
    audit: dict[str, Any], decision: dict[str, Any]
) -> dict[str, Any]:
    reference = dict(audit.get("reference_assessment") or {})
    findings = []
    for finding in decision.get("findings") or []:
        if not isinstance(finding, dict):
            continue
        findings.append(
            {
                key: finding.get(key)
                for key in (
                    "finding_type",
                    "finding_scope",
                    "resolution_state",
                    "title",
                    "severity",
                    "confidence",
                    "expected_behavior",
                    "actual_behavior",
                    "recommended_next_action",
                    "violated_requirement_ids",
                    "violated_contracts",
                    "missing_evidence",
                )
                if finding.get(key) not in (None, [], "")
            }
        )
    return {
        "reference_assessment": reference,
        "calibrated_assessment": audit.get("calibrated") or {},
        "findings": findings,
        "abstained": decision.get("abstain") is True,
        "abstain_reason": decision.get("reason") if decision.get("abstain") is True else None,
    }


def _short(value: Any, limit: int) -> str:
    text = _text(value)
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def _text(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return " ".join(str(value or "").split())


def _percent(value: Any) -> str:
    try:
        return f"{float(value):.0%}"
    except (TypeError, ValueError):
        return "N/A"


def _duration(started_at: Any, ended_at: Any) -> str:
    if not started_at or not ended_at:
        return "duration unavailable"
    try:
        start = datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
        end = datetime.fromisoformat(str(ended_at).replace("Z", "+00:00"))
        milliseconds = max(0, int((end - start).total_seconds() * 1000))
        return f"{milliseconds / 1000:.2f}s" if milliseconds >= 1000 else f"{milliseconds}ms"
    except ValueError:
        return "duration unavailable"
