#!/bin/bash
# Search through all conversation content (case-insensitive)
# Usage: search.sh <conversation.json> <term>
set -euo pipefail
FILE="${1:?Usage: search.sh <conversation.json> <search_term>}"
TERM="${2:?}"
jq --arg t "$TERM" '
  [.conversation[] |
   select(.blocks != null) |
   {line, role} +
   {matches: [.blocks[] |
     select(
       (.text // "" | ascii_downcase | test($t | ascii_downcase)) or
       (.input.command // "" | ascii_downcase | test($t | ascii_downcase)) or
       (.input.file_path // "" | ascii_downcase | test($t | ascii_downcase))
     ) |
     if .type == "text" then {type, excerpt: (.text | splits("\n") | select(test($t; "i")))[0:300]}
     elif .type == "tool_use" then {type: "tool", name, input_summary: (
       if .name == "Bash" then .input.command[:200]
       elif .name == "Read" then .input.file_path
       else (.input | tostring)[:200] end
     )}
     else {type} end
   ]} |
   select(.matches | length > 0)
  ] | .[]' "$FILE"
