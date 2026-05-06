#!/usr/bin/env python3
"""
Claude Code Session Analyzer

Parses a .claude directory and produces a full session report:
timeline, metrics, boundary violations, task state, inefficiency flags.

Usage:
  python3 analyze-session.py <.claude-dir>
  python3 analyze-session.py <.claude-dir> --session-id <uuid>
  python3 analyze-session.py <.claude-dir> --output /tmp/session-report.md

Without --session-id, analyzes the most recent session.
"""

import json
import sys
import os
import glob
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict


def find_latest_session(claude_dir):
    sessions_dir = Path(claude_dir) / "sessions"
    if not sessions_dir.exists():
        return None, None
    session_files = sorted(sessions_dir.glob("*.json"), key=os.path.getmtime, reverse=True)
    if not session_files:
        return None, None
    with open(session_files[0]) as f:
        meta = json.load(f)
    return meta.get("sessionId"), meta


def find_session_by_id(claude_dir, session_id):
    sessions_dir = Path(claude_dir) / "sessions"
    if not sessions_dir.exists():
        return None
    for sf in sessions_dir.glob("*.json"):
        with open(sf) as f:
            meta = json.load(f)
        if meta.get("sessionId") == session_id:
            return meta
    return None


def find_conversation_log(claude_dir, session_id):
    projects_dir = Path(claude_dir) / "projects"
    if not projects_dir.exists():
        return None
    for jsonl in projects_dir.rglob(f"{session_id}.jsonl"):
        return jsonl
    return None


def load_tasks(claude_dir, session_id):
    tasks_dir = Path(claude_dir) / "tasks" / session_id
    if not tasks_dir.exists():
        return []
    tasks = []
    for tf in sorted(tasks_dir.glob("*.json")):
        try:
            with open(tf) as f:
                task = json.load(f)
            task["_file"] = tf.name
            tasks.append(task)
        except (json.JSONDecodeError, IOError):
            pass
    return tasks


def load_history(claude_dir):
    hist_file = Path(claude_dir) / "history.jsonl"
    if not hist_file.exists():
        return []
    entries = []
    with open(hist_file) as f:
        for line in f:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return entries


def parse_conversation(jsonl_path):
    events = []
    with open(jsonl_path) as f:
        for i, line in enumerate(f, 1):
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            events.append((i, msg))
    return events


def extract_messages(events):
    messages = []
    for line_num, msg in events:
        if "message" not in msg or not isinstance(msg["message"], dict):
            # Check for metadata events
            if msg.get("type") == "aiTitle":
                messages.append({
                    "line": line_num,
                    "type": "meta",
                    "subtype": "title",
                    "content": msg.get("aiTitle", "")
                })
            continue

        m = msg["message"]
        role = m.get("role", "")
        content = m.get("content", "")

        if role == "user":
            if isinstance(content, list):
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "text":
                        text = b["text"]
                        if "<command-name>" in text:
                            messages.append({"line": line_num, "type": "user_command", "content": text[:500]})
                        elif "<bash-" in text:
                            messages.append({"line": line_num, "type": "user_shell", "content": text[:500]})
                        else:
                            messages.append({"line": line_num, "type": "user", "content": text[:500]})
            elif isinstance(content, str):
                messages.append({"line": line_num, "type": "user", "content": content[:500]})

        elif role == "assistant":
            if isinstance(content, list):
                for b in content:
                    if not isinstance(b, dict):
                        continue
                    bt = b.get("type", "")
                    if bt == "text" and b.get("text", "").strip():
                        messages.append({"line": line_num, "type": "assistant", "content": b["text"][:500]})
                    elif bt == "tool_use":
                        name = b.get("name", "")
                        inp = b.get("input", {})
                        tool_msg = {"line": line_num, "type": "tool_call", "tool": name, "input": inp}
                        messages.append(tool_msg)

    return messages


def analyze_tool_calls(messages):
    tool_calls = [m for m in messages if m["type"] == "tool_call"]
    counts = Counter(m["tool"] for m in tool_calls)

    # Categorize Bash calls
    bash_calls = [m for m in tool_calls if m["tool"] == "Bash"]
    bash_categories = defaultdict(list)
    for bc in bash_calls:
        cmd = bc["input"].get("command", "")
        if "alvera" in cmd:
            bash_categories["alvera_cli"].append(cmd[:200])
        elif "psql" in cmd or "pg_isready" in cmd:
            bash_categories["postgres"].append(cmd[:200])
        elif "aws " in cmd or "localstack" in cmd:
            bash_categories["aws_s3"].append(cmd[:200])
        elif "find " in cmd:
            bash_categories["find"].append(cmd[:200])
        elif "grep " in cmd:
            bash_categories["grep"].append(cmd[:200])
        elif "npm " in cmd or "npx " in cmd:
            bash_categories["npm"].append(cmd[:200])
        elif "git " in cmd:
            bash_categories["git"].append(cmd[:200])
        elif "cat " in cmd or "ls " in cmd:
            bash_categories["filesystem"].append(cmd[:200])
        elif "curl " in cmd:
            bash_categories["curl"].append(cmd[:200])
        else:
            bash_categories["other"].append(cmd[:200])

    return counts, bash_categories


def detect_boundary_violations(messages):
    violations = []
    for m in messages:
        if m["type"] != "tool_call":
            continue
        tool = m["tool"]
        inp = m["input"]

        path = ""
        if tool == "Read":
            path = inp.get("file_path", "")
        elif tool == "Write":
            path = inp.get("file_path", "")
        elif tool == "Bash":
            cmd = inp.get("command", "")
            # Check for HOME introspection
            if "/.alvera-ai/" in cmd and ("cat " in cmd or "ls " in cmd):
                violations.append({"line": m["line"], "type": "home_introspection", "detail": cmd[:200]})
            if "/credentials" in cmd and "cat " in cmd:
                violations.append({"line": m["line"], "type": "credential_read", "detail": cmd[:200]})
            if "env | grep" in cmd:
                violations.append({"line": m["line"], "type": "env_sniffing", "detail": cmd[:200]})
            # Check for external repo access
            for repo in ["/alvera-platform-sdk/", "/alvera-platform/", "/platform/"]:
                if repo in cmd:
                    violations.append({"line": m["line"], "type": "external_repo", "detail": cmd[:200]})
                    break
            if "/.npm/" in cmd:
                violations.append({"line": m["line"], "type": "npm_cache", "detail": cmd[:200]})
            continue

        if path:
            if "/.alvera-ai/" in path:
                violations.append({"line": m["line"], "type": "home_introspection", "detail": path})
            if "/credentials" in path:
                violations.append({"line": m["line"], "type": "credential_read", "detail": path})
            for repo in ["/alvera-platform-sdk/", "/alvera-platform/", "/platform/"]:
                if repo in path:
                    violations.append({"line": m["line"], "type": "external_repo", "detail": path})
                    break
            if "/.npm/" in path:
                violations.append({"line": m["line"], "type": "npm_cache", "detail": path})

    return violations


def detect_inefficiencies(messages):
    issues = []
    read_files = Counter()
    bash_commands = []

    for m in messages:
        if m["type"] != "tool_call":
            continue
        if m["tool"] == "Read":
            path = m["input"].get("file_path", "")
            read_files[path] += 1
        elif m["tool"] == "Bash":
            bash_commands.append(m["input"].get("command", ""))

    # Excessive reads of same file
    for path, count in read_files.items():
        if count >= 3:
            issues.append(f"Read `{os.path.basename(path)}` {count} times (consider reading once)")

    # CLI auth resolution calls
    auth_calls = [c for c in bash_commands if any(k in c for k in ["whoami", "--version", "which alvera", "tsx"])]
    if len(auth_calls) > 3:
        issues.append(f"{len(auth_calls)} CLI auth/resolution calls (target: 2-3)")

    # find commands (filesystem hunting)
    find_calls = [c for c in bash_commands if c.strip().startswith("find ")]
    if len(find_calls) > 3:
        issues.append(f"{len(find_calls)} `find` commands — possible filesystem hunting")

    # TaskCreate spam (>5 in a row without other actions)
    task_creates = [m for m in messages if m["type"] == "tool_call" and m["tool"] == "TaskCreate"]
    if len(task_creates) > 5:
        issues.append(f"{len(task_creates)} TaskCreate calls — should create tasks lazily")

    return issues


def count_questions(messages):
    questions = []
    for m in messages:
        if m["type"] == "assistant" and "?" in m["content"]:
            questions.append(m["content"][:200])
    return questions


def extract_full_conversation(events):
    """Extract complete conversation as structured JSON — no truncation."""
    conversation = []
    for line_num, msg in events:
        if "message" not in msg or not isinstance(msg["message"], dict):
            if msg.get("type") == "aiTitle":
                conversation.append({
                    "line": line_num,
                    "role": "system",
                    "type": "title",
                    "content": msg.get("aiTitle", "")
                })
            continue

        m = msg["message"]
        role = m.get("role", "")
        content = m.get("content", "")

        if role == "user":
            entry = {"line": line_num, "role": "user", "type": "message", "blocks": []}
            if isinstance(content, list):
                for b in content:
                    if isinstance(b, dict):
                        if b.get("type") == "text":
                            entry["blocks"].append({"type": "text", "text": b["text"]})
                        elif b.get("type") == "tool_result":
                            entry["blocks"].append({
                                "type": "tool_result",
                                "tool_use_id": b.get("tool_use_id", ""),
                                "content": b.get("content", "")[:2000] if isinstance(b.get("content"), str) else str(b.get("content", ""))[:2000]
                            })
                        else:
                            entry["blocks"].append(b)
            elif isinstance(content, str):
                entry["blocks"].append({"type": "text", "text": content})
            conversation.append(entry)

        elif role == "assistant":
            entry = {"line": line_num, "role": "assistant", "type": "message", "blocks": []}
            if isinstance(content, list):
                for b in content:
                    if not isinstance(b, dict):
                        continue
                    bt = b.get("type", "")
                    if bt == "text":
                        entry["blocks"].append({"type": "text", "text": b.get("text", "")})
                    elif bt == "tool_use":
                        entry["blocks"].append({
                            "type": "tool_use",
                            "name": b.get("name", ""),
                            "id": b.get("id", ""),
                            "input": b.get("input", {})
                        })
                    elif bt == "thinking":
                        entry["blocks"].append({"type": "thinking", "text": b.get("thinking", b.get("text", ""))})
                    else:
                        entry["blocks"].append(b)
            conversation.append(entry)

    return conversation


def generate_report(claude_dir, session_id, meta, messages, tasks, history, output_path):
    tool_counts, bash_cats = analyze_tool_calls(messages)
    violations = detect_boundary_violations(messages)
    inefficiencies = detect_inefficiencies(messages)
    questions = count_questions(messages)
    user_messages = [m for m in messages if m["type"] == "user"]
    tool_calls = [m for m in messages if m["type"] == "tool_call"]
    asst_messages = [m for m in messages if m["type"] == "assistant"]

    lines = []
    lines.append(f"# Session Report: `{session_id[:8]}...`\n")
    lines.append(f"**Generated**: {datetime.now().isoformat()[:19]}\n")

    # Metadata
    lines.append("## Metadata\n")
    lines.append(f"| Field | Value |")
    lines.append(f"|-------|-------|")
    lines.append(f"| Session ID | `{session_id}` |")
    lines.append(f"| PID | {meta.get('pid', '?')} |")
    lines.append(f"| Version | {meta.get('version', '?')} |")
    lines.append(f"| CWD | `{meta.get('cwd', '?')}` |")
    lines.append(f"| Started | {meta.get('procStart', '?')} |")
    lines.append(f"| Status | {meta.get('status', '?')} |")
    lines.append("")

    # Metrics
    lines.append("## Metrics\n")
    lines.append(f"| Metric | Count |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Total events (JSONL lines) | {max(m['line'] for m in messages) if messages else 0} |")
    lines.append(f"| User messages | {len(user_messages)} |")
    lines.append(f"| Assistant messages | {len(asst_messages)} |")
    lines.append(f"| Tool calls | {len(tool_calls)} |")
    lines.append(f"| Questions asked | {len(questions)} |")
    for tool, count in tool_counts.most_common(10):
        lines.append(f"| → {tool} | {count} |")
    lines.append("")

    if bash_cats:
        lines.append("### Bash call breakdown\n")
        lines.append(f"| Category | Count |")
        lines.append(f"|----------|-------|")
        for cat, cmds in sorted(bash_cats.items(), key=lambda x: -len(x[1])):
            lines.append(f"| {cat} | {len(cmds)} |")
        lines.append("")

    # Boundary violations
    lines.append("## Boundary Violations\n")
    if violations:
        lines.append(f"**{len(violations)} violations found:**\n")
        for v in violations:
            lines.append(f"- L{v['line']} **{v['type']}**: `{v['detail'][:150]}`")
    else:
        lines.append("None detected.")
    lines.append("")

    # Inefficiencies
    lines.append("## Inefficiency Flags\n")
    if inefficiencies:
        for issue in inefficiencies:
            lines.append(f"- {issue}")
    else:
        lines.append("None detected.")
    lines.append("")

    # Tasks
    lines.append("## Tasks\n")
    if tasks:
        lines.append(f"| # | Status | Description |")
        lines.append(f"|---|--------|-------------|")
        for t in tasks:
            num = t["_file"].replace(".json", "")
            status = t.get("status", "?")
            desc = t.get("description", t.get("subject", ""))[:80]
            lines.append(f"| {num} | {status} | {desc} |")
    else:
        lines.append("No tasks found.")
    lines.append("")

    # Timeline
    lines.append("## Timeline\n")
    lines.append("```")
    for m in messages:
        if m["type"] == "user":
            lines.append(f"L{m['line']:>3} [USER] {m['content'][:200]}")
        elif m["type"] == "user_command":
            lines.append(f"L{m['line']:>3} [CMD]  {m['content'][:200]}")
        elif m["type"] == "assistant":
            text = m["content"][:200].replace("\n", " ")
            lines.append(f"L{m['line']:>3} [ASST] {text}")
        elif m["type"] == "tool_call":
            tool = m["tool"]
            inp = m["input"]
            if tool == "Bash":
                lines.append(f"L{m['line']:>3} [BASH] {inp.get('command', '')[:180]}")
            elif tool == "Read":
                lines.append(f"L{m['line']:>3} [READ] {inp.get('file_path', '')}")
            elif tool == "Write":
                lines.append(f"L{m['line']:>3} [WRIT] {inp.get('file_path', '')}")
            elif tool == "Edit":
                lines.append(f"L{m['line']:>3} [EDIT] {inp.get('file_path', '')}")
            elif tool == "TaskCreate":
                desc = inp.get("description", inp.get("subject", ""))[:100]
                lines.append(f"L{m['line']:>3} [TASK] Create: {desc}")
            elif tool == "TaskUpdate":
                lines.append(f"L{m['line']:>3} [TASK] Update: {json.dumps(inp)[:100]}")
            else:
                lines.append(f"L{m['line']:>3} [TOOL] {tool}: {json.dumps(inp)[:150]}")
        elif m["type"] == "meta":
            lines.append(f"L{m['line']:>3} [META] {m.get('subtype', '')}: {m.get('content', '')}")
    lines.append("```\n")

    # Questions
    if questions:
        lines.append("## Questions Asked by Agent\n")
        for i, q in enumerate(questions[:20], 1):
            lines.append(f"{i}. {q[:200]}")
        lines.append("")

    report = "\n".join(lines)

    with open(output_path, "w") as f:
        f.write(report)

    return report


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Analyze Claude Code session")
    parser.add_argument("claude_dir", help="Path to .claude directory")
    parser.add_argument("--session-id", help="Specific session ID (default: most recent)")
    parser.add_argument("--output", default="/tmp/session-report.md", help="Output path")
    args = parser.parse_args()

    claude_dir = args.claude_dir

    if args.session_id:
        session_id = args.session_id
        meta = find_session_by_id(claude_dir, session_id) or {}
    else:
        session_id, meta = find_latest_session(claude_dir)
        if not session_id:
            print("ERROR: No sessions found")
            sys.exit(1)
        meta = meta or {}

    print(f"Session: {session_id}")
    print(f"Version: {meta.get('version', '?')}, PID: {meta.get('pid', '?')}")

    log_path = find_conversation_log(claude_dir, session_id)
    if not log_path:
        print(f"ERROR: No conversation log found for {session_id}")
        sys.exit(1)

    print(f"Log: {log_path} ({os.path.getsize(log_path) / 1024:.0f}KB)")

    events = parse_conversation(log_path)
    messages = extract_messages(events)
    tasks = load_tasks(claude_dir, session_id)
    history = load_history(claude_dir)

    report = generate_report(claude_dir, session_id, meta, messages, tasks, history, args.output)

    # Write structured JSON conversation
    convo_path = args.output.replace(".md", "-conversation.json")
    full_convo = extract_full_conversation(events)
    convo_output = {
        "session_id": session_id,
        "meta": {
            "version": meta.get("version", "?"),
            "pid": meta.get("pid"),
            "cwd": meta.get("cwd", "?"),
            "started": meta.get("procStart"),
            "status": meta.get("status")
        },
        "stats": {
            "total_messages": len(full_convo),
            "user_messages": sum(1 for m in full_convo if m["role"] == "user"),
            "assistant_messages": sum(1 for m in full_convo if m["role"] == "assistant"),
            "tool_calls": sum(
                1 for m in full_convo if m["role"] == "assistant"
                for b in m.get("blocks", []) if isinstance(b, dict) and b.get("type") == "tool_use"
            )
        },
        "conversation": full_convo
    }
    with open(convo_path, "w") as f:
        json.dump(convo_output, f, indent=2, default=str)

    # Print summary to stdout
    tool_calls = [m for m in messages if m["type"] == "tool_call"]
    violations = detect_boundary_violations(messages)
    inefficiencies = detect_inefficiencies(messages)
    questions = count_questions(messages)

    print(f"\n--- SUMMARY ---")
    print(f"Tool calls: {len(tool_calls)}")
    print(f"User messages: {len([m for m in messages if m['type'] == 'user'])}")
    print(f"Questions asked: {len(questions)}")
    print(f"Boundary violations: {len(violations)}")
    print(f"Inefficiency flags: {len(inefficiencies)}")
    print(f"Tasks: {len(tasks)} ({sum(1 for t in tasks if t.get('status')=='completed')} completed)")
    print(f"\nFull report: {args.output}")
    print(f"Structured conversation: {convo_path}")


if __name__ == "__main__":
    main()
