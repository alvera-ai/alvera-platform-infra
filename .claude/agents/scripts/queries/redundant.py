#!/usr/bin/env python3
"""Find repeated operations: same file read multiple times, same bash command, etc.
Usage: redundant.py <conversation.json>
"""
import json, sys
from collections import Counter, defaultdict

def main():
    with open(sys.argv[1]) as f:
        data = json.load(f)

    reads = Counter()
    bash_cmds = Counter()
    read_lines = defaultdict(list)
    bash_lines = defaultdict(list)

    for msg in data["conversation"]:
        if msg["role"] != "assistant":
            continue
        for b in msg.get("blocks", []):
            if not isinstance(b, dict) or b.get("type") != "tool_use":
                continue
            if b["name"] == "Read":
                path = b["input"].get("file_path", "")
                reads[path] += 1
                read_lines[path].append(msg["line"])
            elif b["name"] == "Bash":
                cmd = b["input"].get("command", "").strip()
                norm = cmd[:120]
                bash_cmds[norm] += 1
                bash_lines[norm].append(msg["line"])

    print("=== REPEATED FILE READS (2+) ===\n")
    for path, count in reads.most_common():
        if count < 2:
            break
        lines = ", ".join(f"L{l}" for l in read_lines[path])
        print(f"  {count}x  {path}")
        print(f"       at {lines}\n")

    print("=== REPEATED BASH COMMANDS (2+) ===\n")
    for cmd, count in bash_cmds.most_common():
        if count < 2:
            break
        lines = ", ".join(f"L{l}" for l in bash_lines[cmd])
        print(f"  {count}x  {cmd}")
        print(f"       at {lines}\n")

if __name__ == "__main__":
    main()
