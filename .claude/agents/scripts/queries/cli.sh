#!/bin/bash
# Extract alvera CLI commands in execution order
# Usage: cli.sh <conversation.json>
set -euo pipefail
FILE="${1:?Usage: cli.sh <conversation.json>}"
jq -r '
  .conversation[] | select(.role == "assistant") |
  . as $msg |
  .blocks[]? | select(.type == "tool_use" and .name == "Bash" and (.input.command | test("alvera"))) |
  "L\($msg.line | tostring | if (. | length) < 4 then (" " * (4 - (. | length))) + . else . end)  \(.input.command | split("\n")[0][:180])"
' "$FILE"
