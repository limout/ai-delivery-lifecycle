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


def can_generate_backlog(current_data, agent_status, generating=False, pending=False):
    """Mirrors canGenerateBacklog() in app/static/index.html."""
    return (
        is_complete_envelope(current_data)
        and agent_status == "ready"
        and not generating
        and not pending
    )


def can_queue_backlog_generate(
    current_data,
    agent_status,
    generating=False,
    pending=False,
    startup_failed=False,
):
    """Mirrors canQueueBacklogGenerate() in app/static/index.html."""
    return (
        is_complete_envelope(current_data)
        and not generating
        and not pending
        and not startup_failed
        and agent_status not in {"not_configured", "unauthorized", "invalid_url"}
        and agent_status in {"ready", "starting", "unknown"}
    )


WAKE_BUDGET_MS = 240000
WAKE_POLL_MS = 3000
IDLE_POLL_MS = 60000
PERMANENT_STATUSES = {"not_configured", "unauthorized", "invalid_url"}


class BacklogWakeUi:
    """Deterministic stand-in for Copilot Backlog wake/generate UI state."""

    def __init__(self):
        self.status = "unknown"
        self.pending_generate = False
        self.generating = False
        self.startup_failed = False
        self.wake_deadline = 0
        self.generate_posts = 0
        self.poll_interval_ms = IDLE_POLL_MS
        self.status_in_flight = False
        self.status_checks = 0
        self.error = ""
        self.retry_visible = False
        self.progress = ""
        self.label = "Backlog Agent availability is unknown."

    def _label(self):
        if self.status == "ready":
            return "Backlog Agent is ready."
        if self.status == "not_configured":
            return "Backlog Agent is not configured on the server."
        if self.status == "invalid_url":
            return "Backlog Agent URL is invalid."
        if self.status == "unauthorized":
            return "Backlog Agent authentication failed."
        if self.startup_failed:
            return "Backlog Agent did not become ready in time."
        if self.status == "starting":
            return "Starting backlog service…"
        if self.status == "unavailable":
            return "Backlog Agent is unavailable."
        return "Backlog Agent availability is unknown."

    def apply_status(self, status, now_ms):
        known = {"ready", "starting", "unavailable", "not_configured", "unauthorized", "invalid_url"}
        next_status = status if status in known else "unavailable"
        if next_status in PERMANENT_STATUSES:
            self.status = next_status
            self.startup_failed = False
            self.pending_generate = False
            self.wake_deadline = 0
        elif next_status == "ready":
            self.status = "ready"
            self.startup_failed = False
            self.wake_deadline = 0
        elif next_status == "unavailable":
            self.status = "unavailable"
            self.startup_failed = True
            self.pending_generate = False
        elif next_status == "starting":
            if not self.wake_deadline:
                self.wake_deadline = now_ms + WAKE_BUDGET_MS
            if now_ms >= self.wake_deadline:
                self.status = "starting"
                self.startup_failed = True
                self.pending_generate = False
            else:
                self.status = "starting"
                self.startup_failed = False
        self.retry_visible = self.startup_failed
        self.label = self._label()
        self.progress = self._progress()
        self.poll_interval_ms = WAKE_POLL_MS if self._needs_wake() else IDLE_POLL_MS

    def _progress(self):
        if not self.generating:
            return ""
        if self.status == "ready":
            return "Generating backlog…"
        return "Starting backlog service…"

    def _needs_wake(self):
        if self.status in PERMANENT_STATUSES or self.startup_failed or self.status == "ready":
            return False
        return self.status in {"starting", "unknown"} or self.pending_generate

    def open_tab(self, now_ms=0):
        if not self.wake_deadline and not self.startup_failed and self.status not in PERMANENT_STATUSES:
            self.wake_deadline = now_ms + WAKE_BUDGET_MS

    def retry(self, now_ms):
        self.startup_failed = False
        self.wake_deadline = now_ms + WAKE_BUDGET_MS
        self.error = ""
        if self.status != "ready":
            self.status = "starting"
        self.retry_visible = False
        self.label = self._label()
        self.poll_interval_ms = WAKE_POLL_MS

    def click_generate(self):
        if self.generating:
            return
        envelope = {"status": "COMPLETE", "workflow_status": "COMPLETE"}
        if not can_queue_backlog_generate(
            envelope,
            self.status,
            generating=self.generating,
            pending=self.pending_generate,
            startup_failed=self.startup_failed,
        ):
            return
        self.pending_generate = self.status != "ready"
        self.generating = True
        self.generate_posts += 1
        self.progress = self._progress()

    def finish_generate(self, *, ok=True, message=""):
        self.generating = False
        self.pending_generate = False
        self.progress = ""
        if not ok:
            self.error = message

    def on_status(self, status, now_ms):
        if self.status_in_flight:
            return
        self.status_in_flight = True
        self.status_checks += 1
        self.apply_status(status, now_ms)
        self.status_in_flight = False
        self.progress = self._progress()


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
                    },
                    {
                        "contract_id": "copilot.workflow_response.v1",
                        "json_path": "$.sow.deliverables[0]",
                        "field_name": "deliverables",
                        "excerpt": "Authenticated portal for enterprise customers",
                    },
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
    assert "backlogPendingGenerate" in source
    assert "if (backlogGenerating || backlogAbort) return;" in source
    assert "AbortController" in source
    assert "pagehide" in INDEX
    assert "cancelBacklogGenerate" in INDEX
    assert "Generating backlog…" in INDEX
    assert "backlogFailureMessage" in source
    assert "selectTab('backlog')" not in source
    assert "generateBacklog()" not in INDEX.split("function selectTab", 1)[1].split("function formatExportSection", 1)[0]


def test_generation_failure_preserves_analysis_contract():
    source = INDEX.split("async function generateBacklog()", 1)[1].split("function asList", 1)[0]
    assert "setBacklogError" in source
    assert "currentData =" not in source
    assert "The outcome is unknown." in source
    assert "resetBacklogForNewWorkflow" not in source


def test_polling_only_while_backlog_visible():
    assert "const BACKLOG_POLL_MS = 60000;" in INDEX
    assert "const BACKLOG_WAKE_POLL_MS = 3000;" in INDEX
    assert "const BACKLOG_WAKE_BUDGET_MS = 240000;" in INDEX
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
    assert "if (backlogPollTimer && backlogPollIntervalMs === interval) return;" in INDEX


def test_cold_start_ui_already_awake():
    ui = BacklogWakeUi()
    ui.open_tab(0)
    ui.on_status("ready", 0)
    assert ui.status == "ready"
    assert ui.label == "Backlog Agent is ready."
    assert ui.poll_interval_ms == IDLE_POLL_MS
    envelope = {"status": "COMPLETE", "workflow_status": "COMPLETE"}
    assert can_generate_backlog(envelope, ui.status) is True
    ui.click_generate()
    assert ui.generate_posts == 1


def test_cold_start_ui_recovers_after_initial_failure():
    ui = BacklogWakeUi()
    ui.open_tab(0)
    ui.on_status("starting", 0)
    assert ui.label == "Starting backlog service…"
    assert ui.poll_interval_ms == WAKE_POLL_MS
    ui.on_status("ready", 3000)
    assert ui.status == "ready"
    assert ui.poll_interval_ms == IDLE_POLL_MS


def test_cold_start_ui_multiple_checks_then_ready():
    ui = BacklogWakeUi()
    ui.open_tab(0)
    for now in (0, 3000, 6000, 9000):
        ui.on_status("starting", now)
        assert ui.status == "starting"
        assert not ui.startup_failed
    ui.on_status("ready", 12000)
    assert ui.status == "ready"
    assert ui.label == "Backlog Agent is ready."


def test_cold_start_ui_timeout_then_retry():
    ui = BacklogWakeUi()
    ui.open_tab(0)
    ui.on_status("starting", 0)
    ui.on_status("starting", 90000)
    assert ui.startup_failed is False
    assert ui.status == "starting"
    ui.on_status("starting", WAKE_BUDGET_MS)
    assert ui.startup_failed is True
    assert ui.retry_visible is True
    assert "did not become ready" in ui.label
    ui.retry(WAKE_BUDGET_MS + 1000)
    assert ui.startup_failed is False
    assert ui.retry_visible is False
    ui.on_status("ready", WAKE_BUDGET_MS + 4000)
    assert ui.status == "ready"


def test_cold_start_ui_invalid_url_does_not_poll():
    ui = BacklogWakeUi()
    ui.open_tab(0)
    ui.on_status("invalid_url", 0)
    assert ui.status == "invalid_url"
    assert "URL is invalid" in ui.label
    envelope = {"status": "COMPLETE", "workflow_status": "COMPLETE"}
    assert can_queue_backlog_generate(envelope, "invalid_url") is False
    ui.click_generate()
    assert ui.generate_posts == 0


def test_cold_start_ui_permanent_config_does_not_retry():
    ui = BacklogWakeUi()
    ui.open_tab(0)
    ui.on_status("not_configured", 0)
    assert ui.status == "not_configured"
    assert ui.poll_interval_ms == IDLE_POLL_MS
    assert ui.pending_generate is False
    envelope = {"status": "COMPLETE", "workflow_status": "COMPLETE"}
    assert can_queue_backlog_generate(envelope, "not_configured") is False
    ui.click_generate()
    assert ui.generate_posts == 0
    assert ui.pending_generate is False


def test_cold_start_ui_unauthorized_stops_wake():
    ui = BacklogWakeUi()
    ui.open_tab(0)
    ui.on_status("unauthorized", 0)
    assert ui.status == "unauthorized"
    assert "authentication failed" in ui.label
    envelope = {"status": "COMPLETE", "workflow_status": "COMPLETE"}
    assert can_queue_backlog_generate(envelope, "unauthorized") is False


def test_concurrent_status_checks_do_not_stack():
    ui = BacklogWakeUi()
    ui.status_in_flight = True
    ui.on_status("ready", 0)
    assert ui.status_checks == 0
    assert ui.status == "unknown"
    ui.status_in_flight = False
    ui.on_status("ready", 0)
    assert ui.status_checks == 1


def test_pending_generate_resumes_once():
    ui = BacklogWakeUi()
    ui.open_tab(0)
    ui.on_status("starting", 0)
    ui.click_generate()
    ui.click_generate()
    assert ui.pending_generate is True
    assert ui.generating is True
    assert ui.generate_posts == 1
    assert ui.progress == "Starting backlog service…"
    ui.on_status("ready", 6000)
    assert ui.generate_posts == 1
    assert ui.progress == "Generating backlog…"
    ui.on_status("ready", 9000)
    assert ui.generate_posts == 1
    ui.finish_generate()
    assert ui.generating is False
    assert ui.progress == ""


def test_generation_failure_stops_spinner():
    ui = BacklogWakeUi()
    ui.open_tab(0)
    ui.on_status("ready", 0)
    ui.click_generate()
    assert ui.progress == "Generating backlog…"
    ui.finish_generate(ok=False, message="Backlog Agent returned an error. (stage: generate, HTTP 500)")
    assert ui.generating is False
    assert ui.progress == ""
    assert "stage: generate" in ui.error
    assert "HTTP 500" in ui.error


def test_duplicate_click_does_not_start_second_generate():
    ui = BacklogWakeUi()
    ui.open_tab(0)
    ui.on_status("ready", 0)
    ui.click_generate()
    ui.click_generate()
    ui.click_generate()
    assert ui.generate_posts == 1
    ui.finish_generate()
    ui.click_generate()
    assert ui.generate_posts == 2


def test_ui_exposes_retry_without_agent_token():
    assert 'id="retryBacklogButton"' in INDEX
    assert "Starting backlog service…" in INDEX
    assert "retryBacklogStartup" in INDEX
    script = INDEX.split("<script>", 1)[1]
    assert "BACKLOG_API_TOKEN" not in script
    assert "Bearer " not in script


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
    assert epic["provenance"][0]["contract_id"] == "copilot.workflow_response.v1"
    assert epic["provenance"][0]["field_name"] == "functional_requirements"
    assert "data-backlog-item" in INDEX
    assert "<h4>Source</h4>" in INDEX
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


def source_excerpts(references):
    """Mirrors sourceExcerpts() in app/static/index.html."""
    items = references if isinstance(references, list) else []
    excerpts = []
    for item in items:
        if not isinstance(item, dict):
            continue
        excerpt = str(item.get("excerpt") or "").strip()
        if excerpt:
            excerpts.append(excerpt)
    return excerpts


def render_provenance_html(references):
    """Mirrors renderProvenance() in app/static/index.html."""
    return "".join(f"<p>{excerpt}</p>" for excerpt in source_excerpts(references))


def test_item_detail_shows_source_excerpts_not_technical_metadata():
    epic = SAMPLE_PAYLOAD["backlog"]["items"][0]
    html = render_provenance_html(epic["provenance"])
    assert "Customers can sign in" in html
    assert "Authenticated portal for enterprise customers" in html
    assert html.index("Customers can sign in") < html.index("Authenticated portal")
    assert "copilot.workflow_response.v1" not in html
    assert "$.requirements.functional_requirements[0]" not in html
    assert "$.sow.deliverables[0]" not in html
    assert "functional_requirements" not in html
    assert "deliverables" not in html
    provenance_fn = INDEX.split("function renderProvenance", 1)[1].split("function renderEffort", 1)[0]
    assert "excerpt" in provenance_fn
    assert "contract_id" not in provenance_fn
    assert "json_path" not in provenance_fn
    assert "field_name" not in provenance_fn
    detail_fn = INDEX.split("function renderBacklogDetail", 1)[1].split("function renderBacklogFindings", 1)[0]
    assert "sourceHtml" in detail_fn
    assert "<h4>Source</h4>" in detail_fn


def test_full_provenance_remains_in_payload_and_raw_json_view():
    refs = SAMPLE_PAYLOAD["backlog"]["items"][0]["provenance"]
    assert len(refs) == 2
    assert refs[0]["contract_id"] == "copilot.workflow_response.v1"
    assert refs[0]["json_path"] == "$.requirements.functional_requirements[0]"
    assert refs[0]["field_name"] == "functional_requirements"
    assert refs[1]["json_path"] == "$.sow.deliverables[0]"
    assert "Show raw backlog JSON" in INDEX
    assert "JSON.stringify(payload, null, 2)" in INDEX
    assert 'id="backlogRawJson"' in INDEX


def test_empty_or_missing_excerpts_do_not_break_the_viewer():
    assert render_provenance_html([]) == ""
    assert render_provenance_html([{"json_path": "$.x", "field_name": "text", "contract_id": "c"}]) == ""
    assert render_provenance_html([{"excerpt": "   "}]) == ""
    assert source_excerpts(SAMPLE_PAYLOAD["backlog"]["items"][1]["provenance"]) == []
    assert "No source references provided." not in INDEX
    assert "No description provided." in INDEX
    finding_fn = INDEX.split("function renderFindingCard", 1)[1].split("function renderBacklogTreeRows", 1)[0]
    assert "renderProvenance(finding.source_references)" in finding_fn
    assert "json_path" not in finding_fn
    warning = SAMPLE_PAYLOAD["findings"]["items"][0]
    warning_html = render_provenance_html(warning["source_references"])
    assert "Enterprise customers need self-service" in warning_html
    assert "$.discovery.problem" not in warning_html
    error = SAMPLE_PAYLOAD["findings"]["items"][1]
    assert render_provenance_html(error["source_references"]) == ""


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
