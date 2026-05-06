#!/usr/bin/env python3
"""Compact timeline: one line per action, grouped by phase.
Usage: timeline.py <conversation.json>
"""
import json, sys

ICONS = {
    "Bash": "SH", "Read": "RD", "Write": "WR", "Edit": "ED",
    "TaskCreate": "T+", "TaskUpdate": "T~", "Agent": "AG",
}

def main():
    with open(sys.argv[1]) as f:
        data = json.load(f)

    phase = 0
    last_role = None
    for msg in data["conversation"]:
        role = msg["role"]
        if role == "user" and last_role != "user":
            phase += 1
            blocks = msg.get("blocks", [])
            text = next((b.get("text", "")[:120] for b in blocks if isinstance(b, dict) and b.get("type") == "text" and not b.get("text", "").startswith("<")), None)
            if text:
                print(f"\n{'='*60}")
                print(f"Phase {phase} (L{msg['line']}): {text}")
                print(f"{'='*60}")

        elif role == "assistant":
            for b in msg.get("blocks", []):
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "tool_use":
                    name = b.get("name", "?")
                    icon = ICONS.get(name, name[:2].upper())
                    inp = b.get("input", {})
                    if name == "Bash":
                        cmd = inp.get("command", "")[:140]
                        print(f"  L{msg['line']:>4} [{icon}] {cmd}")
                    elif name in ("Read", "Write", "Edit"):
                        print(f"  L{msg['line']:>4} [{icon}] {inp.get('file_path', '')}")
                    elif name in ("TaskCreate", "TaskUpdate"):
                        desc = inp.get("description", inp.get("subject", ""))[:80]
                        print(f"  L{msg['line']:>4} [{icon}] {desc}")
                    else:
                        print(f"  L{msg['line']:>4} [{icon}] {json.dumps(inp)[:120]}")
                elif b.get("type") == "text" and b.get("text", "").strip():
                    text = b["text"].strip().replace("\n", " ")[:100]
                    print(f"  L{msg['line']:>4} [..] {text}")

        last_role = role

if __name__ == "__main__":
    main()
