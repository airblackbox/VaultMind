"""
VaultMind LAM Layer — Phase 3
Large Action Model: SLM (Qwen3) in agent mode with tools.
Human-in-the-loop gate for high-risk actions.
Audit trail for every action taken.
"""

import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ── Risk Tiers ─────────────────────────────────────────────────

AUTO_EXECUTE_TOOLS = {
    "search_knowledge_base",
    "tag_document",
    "summarize_document",
    "extract_dates",
    "log_time_entry",
    "move_file_internal",
}

STAGED_TOOLS = {
    "create_document",
    "draft_email",
    "create_calendar_event",
    "check_conflicts",
    "send_email",
}


# ── Audit Trail ────────────────────────────────────────────────

AUDIT_DIR = os.path.join(os.path.dirname(__file__), "lam_audit")
os.makedirs(AUDIT_DIR, exist_ok=True)

def write_audit(
    tool: str,
    params: dict,
    result: Any,
    reasoning: str,
    auto_executed: bool,
    matter_id: str = "",
) -> str:
    """Write a tamper-evident audit record for every LAM action."""
    record_id = str(uuid.uuid4())
    record = {
        "id": record_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "matter_id": matter_id,
        "tool": tool,
        "params": params,
        "reasoning": reasoning,
        "result": str(result)[:2000],
        "auto_executed": auto_executed,
        "risk_tier": "auto" if auto_executed else "staged",
    }
    path = os.path.join(AUDIT_DIR, f"{record_id}.json")
    with open(path, "w") as f:
        json.dump(record, f, indent=2)
    print(f"📋 Audit: [{record['risk_tier'].upper()}] {tool} → {path}")
    return record_id


# ── Staged Action Queue ────────────────────────────────────────

STAGED_QUEUE_FILE = os.path.join(os.path.dirname(__file__), "staged_actions.json")

def load_staged() -> list:
    if os.path.exists(STAGED_QUEUE_FILE):
        try:
            with open(STAGED_QUEUE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return []

def save_staged(actions: list):
    with open(STAGED_QUEUE_FILE, "w") as f:
        json.dump(actions, f, indent=2)

def queue_staged_action(tool: str, params: dict, reasoning: str, matter_id: str = "") -> str:
    """Queue a high-risk action for human review before execution."""
    action_id = str(uuid.uuid4())
    actions = load_staged()
    actions.append({
        "id": action_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool": tool,
        "params": params,
        "reasoning": reasoning,
        "matter_id": matter_id,
        "status": "pending",
    })
    save_staged(actions)
    write_audit(tool, params, "STAGED — awaiting approval", reasoning, False, matter_id)
    return action_id

def approve_staged_action(action_id: str) -> dict:
    """Approve and execute a staged action."""
    actions = load_staged()
    for action in actions:
        if action["id"] == action_id and action["status"] == "pending":
            action["status"] = "approved"
            action["approved_at"] = datetime.now(timezone.utc).isoformat()
            save_staged(actions)
            result = execute_tool(action["tool"], action["params"])
            write_audit(
                action["tool"], action["params"], result,
                action["reasoning"], True, action["matter_id"]
            )
            return {"approved": True, "result": result}
    return {"error": "Action not found or already processed"}

def reject_staged_action(action_id: str) -> dict:
    """Reject a staged action."""
    actions = load_staged()
    for action in actions:
        if action["id"] == action_id and action["status"] == "pending":
            action["status"] = "rejected"
            action["rejected_at"] = datetime.now(timezone.utc).isoformat()
            save_staged(actions)
            return {"rejected": True}
    return {"error": "Action not found or already processed"}


# ── Tool Implementations ───────────────────────────────────────

MATTERS_DIR = os.path.join(os.path.dirname(__file__), "..", "matters")
os.makedirs(MATTERS_DIR, exist_ok=True)

def execute_tool(tool: str, params: dict) -> Any:
    """Dispatch a tool call to its implementation."""
    handlers = {
        "create_document":      _create_document,
        "move_file_internal":   _move_file_internal,
        "tag_document":         _tag_document,
        "summarize_document":   _summarize_document,
        "extract_dates":        _extract_dates,
        "log_time_entry":       _log_time_entry,
        "check_conflicts":      _check_conflicts,
        "draft_email":          _draft_email,
        "create_calendar_event":_create_calendar_event,
    }
    handler = handlers.get(tool)
    if not handler:
        return f"Unknown tool: {tool}"
    try:
        return handler(**params)
    except Exception as e:
        return f"Tool error: {e}"

def _create_document(matter_id: str, doc_type: str, content: str, title: str = "") -> str:
    matter_path = Path(MATTERS_DIR) / matter_id
    matter_path.mkdir(parents=True, exist_ok=True)
    filename = f"{doc_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    if title:
        filename = f"{title.replace(' ', '_')}_{filename}"
    filepath = matter_path / filename
    with open(filepath, "w") as f:
        f.write(f"# {title or doc_type}\n\n{content}")
    return f"Created: {filepath}"

def _move_file_internal(source: str, destination: str) -> str:
    src = Path(source)
    dst = Path(destination)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    return f"Moved: {source} → {destination}"

def _tag_document(file_path: str, tags: list) -> str:
    meta_path = Path(file_path).with_suffix(".tags.json")
    existing = []
    if meta_path.exists():
        with open(meta_path) as f:
            existing = json.load(f).get("tags", [])
    all_tags = list(set(existing + tags))
    with open(meta_path, "w") as f:
        json.dump({"file": file_path, "tags": all_tags}, f)
    return f"Tagged {file_path}: {all_tags}"

def _summarize_document(file_path: str) -> str:
    try:
        with open(file_path) as f:
            content = f.read()[:3000]
        import ollama
        resp = ollama.chat(
            model=os.environ.get("VAULTMIND_SLM_MODEL", "qwen2.5"),
            messages=[{
                "role": "user",
                "content": f"Summarize this document in 3-5 sentences:\n\n{content}"
            }]
        )
        return resp["message"]["content"]
    except Exception as e:
        return f"Could not summarize: {e}"


def _extract_dates(file_path: str) -> str:
    try:
        with open(file_path) as f:
            content = f.read()[:3000]
        import ollama
        resp = ollama.chat(
            model=os.environ.get("VAULTMIND_SLM_MODEL", "qwen2.5"),
            messages=[{
                "role": "user",
                "content": (
                    "Extract all dates, deadlines, and time references from this document. "
                    "Return as a JSON list: [{\"date\": \"...\", \"context\": \"...\"}]\n\n"
                    + content
                )
            }]
        )
        return resp["message"]["content"]
    except Exception as e:
        return f"Could not extract dates: {e}"

def _log_time_entry(matter_id: str, hours: float, description: str) -> str:
    log_path = Path(MATTERS_DIR) / matter_id / "time_log.json"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entries = []
    if log_path.exists():
        with open(log_path) as f:
            entries = json.load(f)
    entries.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hours": hours,
        "description": description,
    })
    with open(log_path, "w") as f:
        json.dump(entries, f, indent=2)
    total = sum(e["hours"] for e in entries)
    return f"Logged {hours}h for {matter_id}. Total: {total}h"

def _check_conflicts(party_names: list) -> str:
    matches = []
    matters_path = Path(MATTERS_DIR)
    if not matters_path.exists():
        return "No matters on file yet."
    for matter_dir in matters_path.iterdir():
        if not matter_dir.is_dir():
            continue
        for file in matter_dir.glob("**/*"):
            if file.is_file() and file.suffix in [".md", ".txt", ".json"]:
                try:
                    content = file.read_text(errors="ignore").lower()
                    for name in party_names:
                        if name.lower() in content:
                            matches.append(f"⚠️  '{name}' found in matter: {matter_dir.name} ({file.name})")
                except Exception:
                    pass
    if not matches:
        return f"No conflicts found for: {', '.join(party_names)}"
    return "\n".join(matches)

def _draft_email(to: str, subject: str, body: str) -> str:
    """Stage an email for attorney review — never auto-sends."""
    staged_path = Path(MATTERS_DIR) / "staged_emails"
    staged_path.mkdir(parents=True, exist_ok=True)
    filename = f"draft_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    draft = {"to": to, "subject": subject, "body": body,
             "status": "draft", "created": datetime.now(timezone.utc).isoformat()}
    with open(staged_path / filename, "w") as f:
        json.dump(draft, f, indent=2)
    return f"Email draft staged for review: {filename} (never auto-sent)"

def _create_calendar_event(title: str, date: str, duration: str = "1h") -> str:
    cal_path = Path(MATTERS_DIR) / "calendar_events.json"
    events = []
    if cal_path.exists():
        with open(cal_path) as f:
            events = json.load(f)
    events.append({"title": title, "date": date, "duration": duration,
                   "created": datetime.now(timezone.utc).isoformat()})
    with open(cal_path, "w") as f:
        json.dump(events, f, indent=2)
    return f"Calendar event staged: {title} on {date} ({duration})"


# ── Main LAM Agent ─────────────────────────────────────────────

TOOL_DEFINITIONS = [
    {
        "name": "search_knowledge_base",
        "description": "Search indexed documents for information. Use this first before any action.",
        "parameters": {"query": "str", "matter_id": "str (optional)"},
        "risk": "auto",
    },
    {
        "name": "create_document",
        "description": "Create a new document in a matter folder (depo prep, timeline, summary).",
        "parameters": {"matter_id": "str", "doc_type": "str", "content": "str", "title": "str"},
        "risk": "staged",
    },
    {
        "name": "extract_dates",
        "description": "Extract all dates and deadlines from a document file.",
        "parameters": {"file_path": "str"},
        "risk": "auto",
    },
    {
        "name": "log_time_entry",
        "description": "Log billable time to a matter.",
        "parameters": {"matter_id": "str", "hours": "float", "description": "str"},
        "risk": "auto",
    },
    {
        "name": "check_conflicts",
        "description": "Check if any party names appear in existing matters (conflict of interest check).",
        "parameters": {"party_names": "list of str"},
        "risk": "auto",
    },
    {
        "name": "draft_email",
        "description": "Stage an email draft for attorney review. NEVER auto-sends.",
        "parameters": {"to": "str", "subject": "str", "body": "str"},
        "risk": "staged",
    },
    {
        "name": "create_calendar_event",
        "description": "Create a calendar event or deadline reminder.",
        "parameters": {"title": "str", "date": "str", "duration": "str"},
        "risk": "staged",
    },
    {
        "name": "tag_document",
        "description": "Add metadata tags to a document for filtering and search.",
        "parameters": {"file_path": "str", "tags": "list of str"},
        "risk": "auto",
    },
]

def run_lam_agent(
    query: str,
    context_chunks: list[str],
    matter_id: str = "",
    model: Optional[str] = None,
) -> dict:
    """
    Run the LAM agent on a user command.
    Returns planned steps, auto-executed results, and staged actions needing approval.
    """
    import ollama

    slm = model or os.environ.get("VAULTMIND_SLM_MODEL", "qwen2.5")
    context = "\n\n".join(context_chunks[:5]) if context_chunks else "No context retrieved."

    tool_list = "\n".join(
        f"- {t['name']} ({t['risk'].upper()}): {t['description']} | params: {t['parameters']}"
        for t in TOOL_DEFINITIONS
    )

    system_prompt = f"""You are VaultMind, a private AI assistant for a law firm.
You have access to these tools:
{tool_list}

AUTO tools execute immediately. STAGED tools require attorney approval.
NEVER send emails or create client-facing documents without staging for review.

Return a JSON plan:
{{
  "reasoning": "why you chose these steps",
  "steps": [
    {{"tool": "tool_name", "params": {{}}, "reason": "why this step"}}
  ]
}}
Return ONLY valid JSON."""

    user_msg = f"""Matter: {matter_id or 'general'}
Context from vault:
{context}

Attorney request: {query}"""

    try:
        resp = ollama.chat(
            model=slm,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
            options={"temperature": 0.2},
        )
        raw = resp["message"]["content"].strip()
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:-1])
        plan = json.loads(raw)
    except Exception as e:
        return {"error": f"LAM planning failed: {e}", "steps": []}

    auto_results = []
    staged_ids = []

    for step in plan.get("steps", []):
        tool = step.get("tool", "")
        params = step.get("params", {})
        reason = step.get("reason", "")

        if tool in AUTO_EXECUTE_TOOLS:
            result = execute_tool(tool, params)
            audit_id = write_audit(tool, params, result, reason, True, matter_id)
            auto_results.append({"tool": tool, "result": result, "audit_id": audit_id})
        elif tool in STAGED_TOOLS:
            action_id = queue_staged_action(tool, params, reason, matter_id)
            staged_ids.append({"tool": tool, "action_id": action_id, "reason": reason})
        else:
            auto_results.append({"tool": tool, "result": f"Unknown tool: {tool}"})

    return {
        "reasoning": plan.get("reasoning", ""),
        "auto_executed": auto_results,
        "staged_for_review": staged_ids,
        "matter_id": matter_id,
    }
