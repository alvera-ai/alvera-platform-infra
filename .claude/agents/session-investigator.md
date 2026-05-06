---
name: session-investigator
description: >
  Investigate Claude Code session history — find conversation logs, tool calls,
  task state, and plugin activity from any .claude directory (real or sandbox).
  Use when debugging skill behavior, auditing agent decisions, or extracting
  what happened in a past session.
---

# Session Investigator Agent

Finds and parses Claude Code session artifacts from a `.claude` directory.

## Directory Anatomy

```
~/.claude/                          # Global (user-level)
├── .claude.json                    # App config, feature flags, tips state
├── .credentials.json               # Auth credentials (DO NOT echo contents)
├── history.jsonl                   # All user inputs across sessions (lightweight index)
├── settings.json                   # Global settings (theme, enabled plugins)
├── sessions/                       # Session metadata
│   └── <pid>.json                  # {pid, sessionId, cwd, startedAt, status, version}
├── projects/                       # Per-project conversation logs
│   └── <project-path-slug>/
│       ├── <sessionId>.jsonl       # Full conversation log (messages + tool calls)
│       ├── memory/                 # Project-specific memories
│       │   ├── MEMORY.md           # Memory index
│       │   └── *.md               # Individual memory files
│       └── CLAUDE.md              # Project-level instructions
├── tasks/                          # Task state per session
│   └── <sessionId>/
│       ├── .lock
│       └── <taskNumber>.json       # {status, description, subject}
├── plans/                          # Saved plans
├── plugins/
│   └── cache/<marketplace>/<plugin>/<version>/  # Cached plugin files
├── backups/                        # Config backups (timestamped)
├── shell-snapshots/                # Shell state snapshots
├── session-env/                    # Session environment variables
└── cache/                          # Misc cache (changelog, etc)
```

## How to Find a Session

### By recency (most common)
```bash
# Latest session
ls -t ~/.claude/sessions/*.json | head -1 | xargs cat | python3 -m json.tool

# All sessions today
find ~/.claude/sessions -name "*.json" -newer /tmp/today_marker
```

### By project
```bash
# List all conversation logs for a project
ls ~/.claude/projects/<project-path-slug>/

# Project path slug = absolute path with / replaced by -
# e.g. /Users/aniketsingh/work/orza/foo → -Users-aniketsingh-work-orza-foo
```

### By session ID
```bash
# If you have the sessionId, find everything:
SESSION_ID="43ac24e1-2f23-42cb-a02f-4ec49f3f4b40"

# Conversation log (in project dir)
find ~/.claude/projects -name "${SESSION_ID}.jsonl"

# Tasks
ls ~/.claude/tasks/${SESSION_ID}/

# Session metadata (by PID)
grep -l "$SESSION_ID" ~/.claude/sessions/*.json
```

## Parsing the Conversation Log (JSONL)

Each line is one event. Key types:

| Key pattern | What it is |
|-------------|-----------|
| `type: "permissionMode"` | Session start/permission change |
| `type: "messageId"` + `snapshot` | Message snapshot (for UI state) |
| `type: "leafUuid"` | Conversation tree pointer |
| `type: "aiTitle"` | Auto-generated session title |
| `type: "lastPrompt"` | Last user prompt (for resume) |
| `type: "operation"` | File operations (edit, write) |
| `message.role: "user"` | User message with content |
| `message.role: "assistant"` | Assistant response (text + tool_use blocks) |
| `message.role: "tool"` | Tool results |

### Extract messages script
```python
import json, sys

with open(sys.argv[1]) as f:
    for i, line in enumerate(f, 1):
        msg = json.loads(line)
        if 'message' not in msg or not isinstance(msg['message'], dict):
            continue
        m = msg['message']
        role = m.get('role', '')
        content = m.get('content', '')
        
        if role == 'user' and isinstance(content, list):
            for b in content:
                if isinstance(b, dict) and b.get('type') == 'text':
                    print(f"L{i} [USER] {b['text'][:300]}")
        elif role == 'assistant' and isinstance(content, list):
            for b in content:
                if isinstance(b, dict):
                    if b.get('type') == 'text' and b.get('text','').strip():
                        print(f"L{i} [ASST] {b['text'][:300]}")
                    elif b.get('type') == 'tool_use':
                        name = b.get('name','')
                        inp = b.get('input',{})
                        if name == 'Bash':
                            print(f"L{i} [CALL] Bash: {inp.get('command','')[:200]}")
                        elif name == 'Read':
                            print(f"L{i} [CALL] Read: {inp.get('file_path','')}")
                        elif name == 'Write':
                            print(f"L{i} [CALL] Write: {inp.get('file_path','')}")
                        else:
                            detail = json.dumps(inp)[:150]
                            print(f"L{i} [CALL] {name}: {detail}")
```

Usage: `python3 parse_session.py ~/.claude/projects/<slug>/<sessionId>.jsonl`

### Extract tool calls only
```bash
python3 -c "
import json, sys
with open(sys.argv[1]) as f:
    for line in f:
        msg = json.loads(line)
        m = msg.get('message', {})
        if not isinstance(m, dict) or m.get('role') != 'assistant':
            continue
        for b in (m.get('content') or []):
            if isinstance(b, dict) and b.get('type') == 'tool_use':
                print(f\"{b['name']}: {json.dumps(b.get('input',{}))[:200]}\")
" "$1"
```

## Reading Tasks

```bash
# All tasks for a session
for f in ~/.claude/tasks/<sessionId>/*.json; do
  echo "=== $(basename $f) ==="
  python3 -c "import json; d=json.load(open('$f')); print(f\"{d.get('status','?')}: {d.get('description','')[:100]}\")"
done
```

Task statuses: `pending`, `in_progress`, `completed`.

## Reading History (User Inputs Only)

```bash
# Quick view of what user typed
python3 -c "
import json
with open('$HOME/.claude/history.jsonl') as f:
    for line in f:
        d = json.loads(line)
        print(f\"{d.get('timestamp','')} | {d.get('display','')[:100]}\")
" | tail -20
```

## Sandbox Sessions

Sandboxes (e.g. `/tmp/alvera.9ZMTps/`) use the same structure under
`<sandbox>/home/.claude/`. The project slug uses the sandbox's project
path (e.g. `-private-tmp-alvera-9ZMTps-project`).

Key difference: sandbox HOME is isolated, so `~/.alvera-ai/` won't exist
unless explicitly symlinked. Auth state from the real user isn't inherited.

## Common Investigation Patterns

### "What did the agent do wrong?"
1. Find the session: `ls -t ~/.claude/sessions/*.json | head -1`
2. Get sessionId from it
3. Find conversation log: `find ~/.claude/projects -name "<sessionId>.jsonl"`
4. Run the extract messages script
5. Look for: redundant questions, unnecessary file reads, wrong tool usage

### "Why did the skill ask so many questions?"
1. Filter for `[USER]` lines in the log — count them
2. Filter for `[ASST]` lines ending in `?` — those are agent questions
3. Check if questions could have been answered by a tool call that came BEFORE

### "Did the agent read my credentials?"
```bash
# Check if it read sensitive files
python3 parse_session.py <log> | grep -i "credential\|password\|secret\|token"
```

### "What was the final state?"
1. Check tasks: `~/.claude/tasks/<sessionId>/`
2. Check if any files were written: grep for `Write:` in tool calls
3. Check git: the project dir may have uncommitted changes
