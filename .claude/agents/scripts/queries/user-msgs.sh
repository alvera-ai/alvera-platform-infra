#!/bin/bash
# Show only user messages (what the human said)
# Usage: user-msgs.sh <conversation.json>
set -euo pipefail
FILE="${1:?Usage: user-msgs.sh <conversation.json>}"
jq -r '
  [.conversation[] | select(.role == "user") |
   {line, text: ([.blocks[]? | select(.type == "text") | .text] | join("\n"))} |
   select(.text != "" and (.text | test("^<") | not))
  ] | to_entries[] |
  "--- Message \(.key + 1) (L\(.value.line)) ---\n\(.value.text)\n"' "$FILE"
