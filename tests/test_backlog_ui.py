"""Frontend contract tests for the Copilot Backlog workspace."""

from pathlib import Path

INDEX = Path("app/static/index.html").read_text(encoding="utf-8")
DELIVERY_PLAN_PANEL = INDEX.split('id="panel-delivery_plan"', 1)[1]
_NEXT = DELIVERY_PLAN_PANEL.find('id="panel-')
DELIVERY_PLAN_PANEL = DELIVERY_PLAN_PANEL if _NEXT < 0 else DELIVERY_PLAN_PANEL[:_NEXT]
TABS = INDEX.split('id="artifactTabs"', 1)[1].split("</div>", 1)[0]
BACKLOG_PANEL = INDEX.split('id="panel-backlog"', 1)[1]
_NEXT_BACKLOG = BACKLOG_PANEL.find('id="panel-')
BACKLOG_PANEL = BACKLOG_PANEL if _NEXT_BACKLOG < 0 else BACKLOG_PANEL[:_NEXT_BACKLOG]


def is_complete_envelope(data):
    """Mirrors isCompleteEnvelope() in app/static/index.html."""
    return (
        isinstance(data, dict)
        and data.get("status") == "COMPLETE"
        and data.get("workflow_status") == "COMPLETE"
    )


def can_generate_backlog(current_data, agent_status, generating=False):
    """Mirrors canGenerateBacklog() in app/static/index.html."""
    return is_complete_envelope(current_data) and agent_status == "ready" and not generating


def should_poll_backlog_status(current_tab, page_hidden):
    """Mirrors shouldPollBacklogStatus() in app/static/index.html."""
    return current_tab == "backlog" and not page_hidden


def workflow_key(data):
    """Mirrors workflowKey() in app/static/index.html."""
    if not isinstance(data, dict):
        return ""
    run_id = data.get("run_id")
    return str(run_id) if run_id else ""


def result_belongs_to_workflow(result_key, data):
    key = workflow_key(data)
    return bool(result_key) and bool(key) and result_key == key


def backlog_items(payload):
    """Mirrors backlogItems() in app/static/index.html."""
    backlog = payload.get("backlog") if isinstance(payload, dict) else None
    if isinstance(backlog, list):
        return [item for item in backlog if isinstance(item, dict)]
    if isinstance(backlog, dict):
        items = backlog.get("items") or []
        return [item for item in items if isinstance(item, dict)]
    return []


def backlog_findings(payload):
    """Mirrors backlogFindings() in app/static/index.html."""
    findings = payload.get("findings") if isinstance(payload, dict) else None
    if isinstance(findings, list):
        return [item for item in findings if isinstance(item, dict)]
    if isinstance(findings, dict):
        items = findings.get("items") or []
        return [item for item in items if isinstance(item, dict)]
    return []


def build_backlog_index(payload):
    """Mirrors buildBacklogIndex() in app/static/index.html."""
    items = backlog_items(payload)
    by_id = {
        str(item.get("canonical_id")): item
        for item in items
        if item.get("canonical_id")
    }
    placed = set()
    missing_children = []

    def make_node(item, depth):
        item_id = str(item.get("canonical_id") or "")
        if item_id:
            placed.add(item_id)
        children = []
        for child_id in item.get("child_ids") or []:
            child = by_id.get(str(child_id))
            if child is None:
                missing_children.append({"parentId": item_id, "childId": str(child_id)})
                continue
            children.append(make_node(child, depth + 1))
        return {"item": item, "children": children, "depth": depth}

    roots = []
    unplaced = []
    for item in items:
        parent_id = str(item.get("parent_id") or "")
        if parent_id and parent_id in by_id:
            continue
        item_id = str(item.get("canonical_id") or "")
        if item_id and item_id in placed:
            continue
        if not item_id:
            unplaced.append({"item": item, "children": [], "depth": 0})
            continue
        if parent_id and parent_id not in by_id:
            unplaced.append(make_node(item, 0))
            continue
        roots.append(make_node(item, 0))
    for item in items:
        item_id = str(item.get("canonical_id") or "")
        if not item_id:
            if not any(node["item"] is item for node in unplaced):
                unplaced.append({"item": item, "children": [], "depth": 0})
        elif item_id not in placed:
            unplaced.append(make_node(item, 0))
    return {
        "items": items,
        "roots": roots,
        "unplaced": unplaced,
        "missing_children": missing_children,
        "findings": backlog_findings(payload),
    }


SAMPLE_PAYLOAD = {
    "backlog": {
        "contract_id": "canonical.backlog.v1",
        "backlog_id": "cbl_root",
        "items": [
            {
                "canonical_id": "cbl_epic",
                "type": "epic",
                "title": "Portal access",
                "description": "Enterprise customers can use the portal.",
                "status": "todo",
                "priority": "high",
                "parent_id": None,
                "child_ids": ["cbl_feature"],
                "acceptance_criteria": ["Customers can sign in"],
                "test_requirements": ["Sign-in is tested"],
                "dependencies": [],
                "provenance": [
                    {
                        "contract_id": "copilot.workflow_response.v1",
                        "json_path": "$.requirements.functional_requirements[0]",
                        "field_name": "functional_requirements",
                        "excerpt": "Customers can sign in",
                    }
                ],
                "effort": {"story_points": 5},
            },
            {
                "canonical_id": "cbl_feature",
                "type": "feature",
                "title": "Account login",
                "description": "",
                "status": "todo",
                "parent_id": "cbl_epic",
                "child_ids": ["cbl_story"],
                "acceptance_criteria": [],
                "test_requirements": [],
                "dependencies": [],
                "provenance": [],
            },
            {
                "canonical_id": "cbl_story",
                "type": "user_story",
                "title": "Sign in with Entra ID",
                "parent_id": "cbl_feature",
                "child_ids": ["cbl_task"],
                "acceptance_criteria": [],
                "test_requirements": [],
                "dependencies": [],
                "provenance": [],
            },
            {
                "canonical_id": "cbl_task",
                "type": "task",
                "title": "Configure identity provider",
                "parent_id": "cbl_story",
                "child_ids": ["cbl_subtask"],
                "acceptance_criteria": [],
                "test_requirements": [],
                "dependencies": [],
                "provenance": [],
            },
            {
                "canonical_id": "cbl_subtask",
                "type": "subtask",
                "title": "Register the app",
                "parent_id": "cbl_task",
                "child_ids": [],
                "acceptance_criteria": [],
                "test_requirements": [],
                "dependencies": [],
                "provenance": [],
            },
            {
                "canonical_id": "cbl_orphan",
                "type": "note",
                "title": "Unplaced item",
                "parent_id": "cbl_missing_parent",
                "child_ids": ["cbl_missing_child"],
                "acceptance_criteria": [],
                "test_requirements": [],
                "dependencies": [],
                "provenance": [],
            },
        ],
    },
    "findings": {
        "contract_id": "generation.findings.v1",
        "items": [
            {
                "severity": "warning",
                "code": "GENERATED_CONTENT",
                "message": "Title was generated from source text.",
                "canonical_ids": ["cbl_epic"],
                "source_references": [
                    {
                        "json_path": "$.discovery.problem",
                        "excerpt": "Enterprise customers need self-service",
                    }
                ],
            },
            {
                "severity": "error",
                "code": "UNCOVERED_FUNCTIONAL_REQUIREMENT",
                "message": "A requirement is uncovered.",
                "canonical_ids": [],
                "source_references": [
                    {"json_path": "$.requirements.functional_requirements[1]"}
                ],
            },
        ],
    },
}


def test_backlog_nav_sits_below_outputs():
    assert TABS.find("tab-group-outputs") < TABS.find("tab-group-backlog")
    outputs = TABS.split("tab-group-outputs", 1)[1].split("tab-group-backlog", 1)[0]
    assert "Proposal" in outputs
    assert "SOW" in outputs
    backlog = TABS.split("tab-group-backlog", 1)[1]
    assert 'data-tab="backlog"' in backlog
    assert "Generate" in backlog
    assert "Integrate" in backlog
    assert "Coming later" in backlog
    assert 'id="backlogIntegrateNav"' in backlog
    assert "disabled" in backlog.split("id=\"backlogIntegrateNav\"", 1)[1][:200]


def test_generate_opens_backlog_workspace():
    assert "selectTab('backlog')" in TABS
    assert 'id="panel-backlog"' in INDEX
    assert ">Backlog<" in BACKLOG_PANEL
    assert "Generate Backlog" in BACKLOG_PANEL
    assert "Coming later" in BACKLOG_PANEL
    assert "Generate Backlog" not in DELIVERY_PLAN_PANEL


def test_integrate_is_disabled_and_sends_no_requests():
    integrate = INDEX.split("async function generateBacklog", 1)[1]
    assert "backlogIntegrate" not in integrate.split("function asList", 1)[0]
    assert "selectTab('backlog_integrate')" not in INDEX
    assert 'id="backlogIntegrateButton"' in BACKLOG_PANEL
    assert "disabled" in BACKLOG_PANEL.split('id="backlogIntegrateButton"', 1)[1][:80]
    fetch_calls = [
        line.strip()
        for line in INDEX.splitlines()
        if "fetch(" in line
    ]
    assert any('fetch("/backlog/status")' in line for line in fetch_calls)
    assert any('fetch("/backlog"' in line or 'fetch("/backlog",' in line for line in fetch_calls)
    assert not any("dev.azure.com" in line.lower() for line in fetch_calls)
    assert not any("/generate" in line for line in fetch_calls)


def test_ui_never_calls_backlog_agent_or_exposes_token():
    forbidden = (
        "BACKLOG_API_TOKEN",
        "Authorization",
        "Bearer ",
        "BACKLOG_AGENT_URL",
        "backlog-agent",
        "/generate",
    )
    script = INDEX.split("<script>", 1)[1]
    for marker in forbidden:
        assert marker not in script
    assert 'fetch("/backlog"' in script
    assert 'fetch("/backlog/status")' in script


def test_generate_starts_disabled():
    button = BACKLOG_PANEL.split('id="generateBacklogButton"', 1)[1].split("</button>", 1)[0]
    assert "disabled" in button
    assert can_generate_backlog(None, "unknown") is False
    assert can_generate_backlog({"status": "NEEDS_INFO", "workflow_status": "NEEDS_INFO"}, "ready") is False
    assert can_generate_backlog({"status": "COMPLETE"}, "ready") is False
    assert can_generate_backlog({"status": "COMPLETE", "workflow_status": "COMPLETE"}, "unknown") is False
    assert can_generate_backlog({"status": "COMPLETE", "workflow_status": "COMPLETE"}, "starting") is False
    assert can_generate_backlog({"status": "COMPLETE", "workflow_status": "COMPLETE"}, "unavailable") is False


def test_ready_status_and_complete_workflow_enable_generation():
    envelope = {"status": "COMPLETE", "workflow_status": "COMPLETE", "run_id": "run-1"}
    assert can_generate_backlog(envelope, "ready") is True
    assert can_generate_backlog(envelope, "ready", generating=True) is False


def test_generate_posts_copilot_backlog_once_with_envelope():
    source = INDEX.split("async function generateBacklog()", 1)[1].split("function asList", 1)[0]
    assert source.count('fetch("/backlog"') == 1
    assert "JSON.stringify(envelope)" in source
    assert "const envelope = currentData;" in source
    assert "isCompleteEnvelope(envelope)" in source
    assert "backlogGenerating" in source
    assert "retry" not in source.lower()
    assert "selectTab('backlog')" not in source
    open_workspace = INDEX.split("function startBacklogStatusPolling", 1)[0]
    assert "generateBacklog()" not in INDEX.split("function selectTab", 1)[1].split("function formatExportSection", 1)[0]


def test_generation_failure_preserves_analysis_contract():
    source = INDEX.split("async function generateBacklog()", 1)[1].split("function asList", 1)[0]
    assert "setBacklogError" in source
    assert "currentData =" not in source
    assert "The outcome is unknown." in source
    assert "resetBacklogForNewWorkflow" not in source


def test_polling_only_while_backlog_visible():
    assert "const BACKLOG_POLL_MS = 60000;" in INDEX
    assert "function shouldPollBacklogStatus()" in INDEX
    assert 'currentArtifactTab === "backlog" && !document.hidden' in INDEX
    assert "visibilitychange" in INDEX
    assert "stopBacklogStatusPolling" in INDEX
    assert "startBacklogStatusPolling" in INDEX
    select_tab = INDEX.split("function selectTab", 1)[1].split("function formatExportSection", 1)[0]
    assert 'tabName === "backlog"' in select_tab
    assert "startBacklogStatusPolling()" in select_tab
    assert "stopBacklogStatusPolling()" in select_tab
    assert should_poll_backlog_status("backlog", False) is True
    assert should_poll_backlog_status("backlog", True) is False
    assert should_poll_backlog_status("estimate", False) is False
    assert "if (backlogStatusInFlight) return;" in INDEX
    assert "if (!shouldPollBacklogStatus()) return;" in INDEX.split("async function checkBacklogStatus", 1)[1]


def test_new_analysis_does_not_keep_previous_backlog():
    assert "resetBacklogForNewWorkflow();" in INDEX.split("async function analyze()", 1)[1].split("async function clarify()", 1)[0]
    assert "resetBacklogForNewWorkflow();" in INDEX.split("async function clarify()", 1)[1].split("const BACKLOG_POLL_MS", 1)[0]
    assert "function syncBacklogWithWorkflow" in INDEX
    assert result_belongs_to_workflow("run-1", {"run_id": "run-1"}) is True
    assert result_belongs_to_workflow("run-1", {"run_id": "run-2"}) is False
    assert result_belongs_to_workflow("run-1", {"status": "COMPLETE"}) is False


def finding_severity_key(finding):
    """Mirrors findingSeverityKey() in app/static/index.html."""
    raw = str((finding or {}).get("severity") or "").strip().lower()
    if raw in {"error", "warning", "info"}:
        return raw
    return raw or "unspecified"


def finding_code_key(finding):
    """Mirrors findingCodeKey() in app/static/index.html."""
    code = (finding or {}).get("code")
    if code is None or code == "":
        return ""
    return str(code)


def group_findings_by_severity_and_code(findings):
    """Mirrors groupFindingsBySeverityAndCode() in app/static/index.html."""
    buckets = {"error": [], "warning": [], "info": []}
    extras = []
    extra_seen = {}
    for finding in findings:
        key = finding_severity_key(finding)
        if key in buckets:
            buckets[key].append(finding)
            continue
        if key not in extra_seen:
            extra_seen[key] = []
            extras.append((key, extra_seen[key]))
        extra_seen[key].append(finding)

    def group_codes(items):
        order = []
        by_code = {}
        for finding in items:
            code = finding_code_key(finding)
            if code not in by_code:
                by_code[code] = []
                order.append(code)
            by_code[code].append(finding)
        return [{"code": code, "items": by_code[code]} for code in order]

    sections = []
    for severity, label in (("error", "Errors"), ("warning", "Warnings"), ("info", "Info")):
        items = buckets[severity]
        if items:
            sections.append({"severity": severity, "label": label, "items": items, "codes": group_codes(items)})
    for severity, items in extras:
        if items:
            sections.append({"severity": severity, "label": severity, "items": items, "codes": group_codes(items)})
    return sections


def test_viewer_renders_canonical_hierarchy_and_findings():
    index = build_backlog_index(SAMPLE_PAYLOAD)
    types = [node["item"]["type"] for node in _flatten(index["roots"])]
    assert types == ["epic", "feature", "user_story", "task", "subtask"]
    assert index["unplaced"][0]["item"]["canonical_id"] == "cbl_orphan"
    assert index["missing_children"][0]["childId"] == "cbl_missing_child"
    findings = index["findings"]
    assert [item["severity"] for item in findings] == ["warning", "error"]
    epic = SAMPLE_PAYLOAD["backlog"]["items"][0]
    assert epic["provenance"][0]["json_path"] == "$.requirements.functional_requirements[0]"
    assert epic["provenance"][0]["excerpt"] == "Customers can sign in"
    assert "data-backlog-item" in INDEX
    assert "Source references" in INDEX
    assert "json_path" in INDEX
    assert "Acceptance criteria" in INDEX
    assert "Test requirements" in INDEX
    assert "Show raw backlog JSON" in INDEX
    assert "Items outside the expected hierarchy" in INDEX
    assert "Quality Findings" in INDEX
    assert "data-findings-root" in INDEX
    assert "groupFindingsBySeverityAndCode" in INDEX
    render_fn = INDEX.split("function renderBacklogFindings", 1)[1].split("function renderBacklogViewer", 1)[0]
    assert "generateBacklog" not in render_fn
    assert "currentData =" not in render_fn
    assert "preserved ? !!preserved.root : false" in INDEX
    assert 'groupKey === "severity:error"' in INDEX
    assert 'groupKey === "severity:warning"' in INDEX


def test_findings_are_grouped_without_merging_or_dropping():
    findings = [
        {"severity": "info", "code": "GENERATED_CONTENT", "message": "Title inferred A"},
        {"severity": "warning", "code": "AMBIGUOUS_DECOMPOSITION", "message": "Ambiguous one"},
        {"severity": "info", "code": "ATOMIC_STORY", "message": "Atomic one"},
        {"severity": "info", "code": "GENERATED_CONTENT", "message": "Title inferred B"},
        {"severity": "error", "code": "UNCOVERED_FUNCTIONAL_REQUIREMENT", "message": "Missing FR"},
        {"severity": "warning", "code": "AMBIGUOUS_DECOMPOSITION", "message": "Ambiguous two"},
    ]
    sections = group_findings_by_severity_and_code(findings)
    assert [section["severity"] for section in sections] == ["error", "warning", "info"]
    assert [section["label"] for section in sections] == ["Errors", "Warnings", "Info"]
    generated = next(
        group
        for section in sections
        if section["severity"] == "info"
        for group in section["codes"]
        if group["code"] == "GENERATED_CONTENT"
    )
    assert [item["message"] for item in generated["items"]] == [
        "Title inferred A",
        "Title inferred B",
    ]
    flat = [item for section in sections for group in section["codes"] for item in group["items"]]
    assert len(flat) == 6
    assert {item["message"] for item in findings} == {item["message"] for item in flat}


def test_empty_and_unknown_fields_are_not_invented():
    payload = {
        "backlog": {"items": [{"canonical_id": "cbl_x", "type": "mystery", "title": "X", "child_ids": []}]},
        "findings": {"items": []},
    }
    index = build_backlog_index(payload)
    item = index["items"][0]
    assert item.get("acceptance_criteria") is None
    assert index["findings"] == []
    assert "No description provided." in INDEX
    assert "No findings returned." in INDEX


def _flatten(nodes):
    rows = []
    for node in nodes:
        rows.append(node)
        rows.extend(_flatten(node["children"]))
    return rows
