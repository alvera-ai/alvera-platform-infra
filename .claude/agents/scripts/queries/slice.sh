#!/bin/bash
# Slice conversation between two JSONL line numbers
# Usage: slice.sh <conversation.json> <start_line> <end_line>
set -euo pipefail
FILE="${1:?Usage: slice.sh <conversation.json> <start> <end>}"
START="${2:?}"
END="${3:?}"
jq --argjson s "$START" --argjson e "$END" \
  '[.conversation[] | select(.line >= $s and .line <= $e)] |
   .[] | {line, role, type} +
   (if .blocks then
     {content: [.blocks[] |
       if .type == "text" then {type, text: (.text[:300])}
       elif .type == "tool_use" then {type, name, input}
       else {type}
       end
     ]}
   else {} end)' "$FILE"
