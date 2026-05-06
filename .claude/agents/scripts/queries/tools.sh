#!/bin/bash
# List all tool calls with name and key input fields
# Usage: tools.sh <conversation.json> [tool_name_filter]
set -euo pipefail
FILE="${1:?Usage: tools.sh <conversation.json> [tool_name]}"
FILTER="${2:-}"
if [ -n "$FILTER" ]; then
  jq --arg f "$FILTER" '
    [.conversation[] | select(.role == "assistant") | .blocks[]? |
     select(.type == "tool_use" and .name == $f)] |
    to_entries[] | {
      i: (.key + 1),
      name: .value.name,
      input: (
        if .value.name == "Bash" then .value.input.command[:200]
        elif .value.name == "Read" then .value.input.file_path
        elif .value.name == "Write" then .value.input.file_path
        elif .value.name == "Edit" then .value.input.file_path
        else (.value.input | tostring)[:200]
        end
      )
    }' "$FILE"
else
  jq '
    [.conversation[] | select(.role == "assistant") | .blocks[]? |
     select(.type == "tool_use")] |
    group_by(.name) | map({tool: .[0].name, count: length}) |
    sort_by(-.count)' "$FILE"
fi
