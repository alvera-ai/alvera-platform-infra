#!/usr/bin/env python3
"""Show each boundary violation with surrounding conversation context.
Usage: violations.py <conversation.json> [window=3]
"""
import json, sys

def summarize_block(b):
    if not isinstance(b, dict):
        return ""
    t = b.get("type", "")
    if t == "text":
        return b.get("text", "")[:200].replace("\n", " ")
    if t == "tool_use":
        name = b.get("name", "")
        inp = b.get("input", {})
        if name == "Bash":
            return f"[Bash] {inp.get('command', '')[:150]}"
        if name in ("Read", "Write", "Edit"):
            return f"[{name}] {inp.get('file_path', '')}"
        return f"[{name}] ..."
    return ""

def find_violations_from_json(convo):
    violations = []
    for msg in convo:
        if msg["role"] != "assistant":
            continue
        for b in msg.get("blocks", []):
            if not isinstance(b, dict) or b.get("type") != "tool_use":
                continue
            name = b.get("name", "")
            inp = b.get("input", {})
            path = ""
            if name in ("Read", "Write"):
                path = inp.get("file_path", "")
            elif name == "Bash":
                cmd = inp.get("command", "")
                for pattern, vtype in [
                    ("/.alvera-ai/", "home_introspection"),
                    ("/credentials", "credential_read"),
                    ("env | grep", "env_sniffing"),
                    ("/.npm/", "npm_cache"),
                ]:
                    if pattern in cmd:
                        violations.append({"line": msg["line"], "type": vtype, "detail": cmd[:200]})
                for repo in ["/alvera-platform-sdk/", "/alvera-platform/", "/platform/"]:
                    if repo in cmd:
                        violations.append({"line": msg["line"], "type": "external_repo", "detail": cmd[:200]})
                        break
                continue

            if path:
                for pattern, vtype in [
                    ("/.alvera-ai/", "home_introspection"),
                    ("/credentials", "credential_read"),
                    ("/.npm/", "npm_cache"),
                ]:
                    if pattern in path:
                        violations.append({"line": msg["line"], "type": vtype, "detail": path})
                for repo in ["/alvera-platform-sdk/", "/alvera-platform/", "/platform/"]:
                    if repo in path:
                        violations.append({"line": msg["line"], "type": "external_repo", "detail": path})
                        break
    return violations

def main():
    with open(sys.argv[1]) as f:
        data = json.load(f)

    window = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    convo = data["conversation"]
    violations = find_violations_from_json(convo)

    if not violations:
        print("No boundary violations found.")
        return

    print(f"Found {len(violations)} violations:\n")

    for i, v in enumerate(violations, 1):
        print(f"{'='*60}")
        print(f"Violation {i}: {v['type']} (L{v['line']})")
        print(f"Detail: {v['detail'][:200]}")
        print(f"{'-'*60}")

        idx = next((j for j, m in enumerate(convo) if m["line"] >= v["line"]), None)
        if idx is not None:
            start = max(0, idx - window)
            end = min(len(convo), idx + window + 1)
            for m in convo[start:end]:
                marker = ">>>" if m["line"] == v["line"] else "   "
                role = m["role"][:4].upper()
                blocks = m.get("blocks", [])
                summary = " | ".join(filter(None, (summarize_block(b) for b in blocks)))[:250]
                print(f"  {marker} L{m['line']:>4} [{role}] {summary}")
        print()

if __name__ == "__main__":
    main()
