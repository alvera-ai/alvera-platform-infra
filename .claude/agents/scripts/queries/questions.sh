#!/bin/bash
# Extract all questions the agent asked the user
# Usage: questions.sh <conversation.json>
set -euo pipefail
FILE="${1:?Usage: questions.sh <conversation.json>}"
jq -r '
  [.conversation[] | select(.role == "assistant") |
   {line, texts: [.blocks[]? | select(.type == "text" and (.text | test("\\?"))) | .text]} |
   select(.texts | length > 0)
  ] | to_entries[] |
  "\(.key + 1). (L\(.value.line)) \(.value.texts | join(" ") | gsub("\n"; " ") | .[0:300])"' "$FILE"
