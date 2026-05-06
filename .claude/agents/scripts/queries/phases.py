#!/usr/bin/env python3
"""Show work done in each phase (between user messages) — spot wasted cycles.
Usage: phases.py <conversation.json>
"""
import json, sys
from collections import Counter

def main():
    with open(sys.argv[1]) as f:
        data = json.load(f)

    convo = data["conversation"]
    phases = []
    current_phase = {"user_msg": "", "line": 0, "tools": [], "text_count": 0}

    for msg in convo:
        if msg["role"] == "user":
            blocks = msg.get("blocks", [])
            text = next(
                (b.get("text", "")[:150] for b in blocks
                 if isinstance(b, dict) and b.get("type") == "text"
                 and not b.get("text", "").startswith("<")),
                None
            )
            if text:
                if current_phase["tools"] or current_phase["text_count"]:
                    phases.append(current_phase)
                current_phase = {"user_msg": text, "line": msg["line"], "tools": [], "text_count": 0}

        elif msg["role"] == "assistant":
            for b in msg.get("blocks", []):
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "tool_use":
                    name = b.get("name", "")
                    inp = b.get("input", {})
                    summary = ""
                    if name == "Bash":
                        summary = inp.get("command", "")[:100]
                    elif name in ("Read", "Write", "Edit"):
                        summary = inp.get("file_path", "").split("/")[-1]
                    elif name in ("TaskCreate", "TaskUpdate"):
                        summary = inp.get("description", "")[:60]
                    current_phase["tools"].append((name, summary))
                elif b.get("type") == "text" and b.get("text", "").strip():
                    current_phase["text_count"] += 1

    if current_phase["tools"] or current_phase["text_count"]:
        phases.append(current_phase)

    for i, phase in enumerate(phases, 1):
        tool_counts = Counter(t[0] for t in phase["tools"])
        total = len(phase["tools"])
        counts_str = ", ".join(f"{n}:{c}" for n, c in tool_counts.most_common())

        print(f"\n{'='*60}")
        print(f"Phase {i} (L{phase['line']}) — {total} tool calls, {phase['text_count']} text blocks")
        print(f"User: {phase['user_msg']}")
        print(f"Tools: {counts_str}")
        if total > 8:
            print(f"  ⚠️  Heavy phase — {total} tool calls")
        print(f"{'-'*40}")
        for name, summary in phase["tools"]:
            icon = {"Bash": "SH", "Read": "RD", "Write": "WR", "Edit": "ED",
                    "TaskCreate": "T+", "TaskUpdate": "T~"}.get(name, name[:2])
            print(f"  [{icon}] {summary}")

if __name__ == "__main__":
    main()
