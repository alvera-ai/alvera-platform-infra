#!/usr/bin/env python3
"""Show N messages around a given line number — useful for investigating violations.
Usage: context.py <conversation.json> <line_number> [window=5]
"""
import json, sys

def summarize_block(b):
    if not isinstance(b, dict):
        return str(b)[:100]
    t = b.get("type", "")
    if t == "text":
        return b.get("text", "")[:300]
    if t == "tool_use":
        name = b.get("name", "")
        inp = b.get("input", {})
        if name == "Bash":
            return f"[Bash] {inp.get('command', '')[:200]}"
        if name == "Read":
            return f"[Read] {inp.get('file_path', '')}"
        if name == "Write":
            return f"[Write] {inp.get('file_path', '')}"
        if name == "Edit":
            return f"[Edit] {inp.get('file_path', '')}"
        return f"[{name}] {json.dumps(inp)[:150]}"
    if t == "tool_result":
        return f"[result] {str(b.get('content', ''))[:200]}"
    if t == "thinking":
        return f"[thinking] {b.get('text', b.get('thinking', ''))[:200]}"
    return f"[{t}]"

def main():
    with open(sys.argv[1]) as f:
        data = json.load(f)
    target = int(sys.argv[2])
    window = int(sys.argv[3]) if len(sys.argv) > 3 else 5

    convo = data["conversation"]
    idx = None
    for i, m in enumerate(convo):
        if m["line"] >= target:
            idx = i
            break
    if idx is None:
        print(f"Line {target} not found")
        return

    start = max(0, idx - window)
    end = min(len(convo), idx + window + 1)

    for m in convo[start:end]:
        marker = ">>>" if m["line"] == target else "   "
        role = m["role"].upper()[:4]
        blocks = m.get("blocks", [])
        summary = " | ".join(summarize_block(b) for b in blocks) if blocks else m.get("content", "")[:200]
        print(f"{marker} L{m['line']:>4} [{role}] {summary[:250]}")

if __name__ == "__main__":
    main()
