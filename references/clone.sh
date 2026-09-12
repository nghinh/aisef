#!/bin/bash
set -u
repos="
bmad-method|https://github.com/bmad-code-org/bmad-method
karpathy-skills|https://github.com/multica-ai/andrej-karpathy-skills
ui-ux-pro-max|https://github.com/nextlevelbuilder/ui-ux-pro-max-skill
cybersecurity-skills|https://github.com/mukul975/anthropic-cybersecurity-skills
deepseek-harness|https://github.com/deepseek-ai/deepseek-harness
spec-kit|https://github.com/github/spec-kit
superpowers|https://github.com/obra/superpowers
agentskills|https://github.com/agentskills/agentskills
context7|https://github.com/upstash/context7
serena|https://github.com/oraios/serena
gitnexus|https://github.com/abhigyanpatwari/GitNexus
playwright-mcp|https://github.com/microsoft/playwright-mcp
"
echo "$repos" | grep -v '^$' | while IFS='|' read -r name url; do
  if [ -d "$name/.git" ]; then echo "SKIP $name"; continue; fi
  echo "CLONE $name"
  git clone --quiet --depth 1 --no-tags "$url" "$name" 2>&1 | tail -2 || echo "FAIL $name"
done
echo "--- PINS ---"
{
  echo "# Pinned references"
  echo
  echo "Ngày clone: $(date +%Y-%m-%d). Clone \`--depth 1\`; commit là HEAD của default branch tại thời điểm clone."
  echo
  echo "| Repo | URL | Commit | Commit date | Default branch |"
  echo "|---|---|---|---|---|"
  echo "$repos" | grep -v '^$' | while IFS='|' read -r name url; do
    if [ -d "$name/.git" ]; then
      sha=$(git -C "$name" rev-parse HEAD)
      d=$(git -C "$name" log -1 --format=%cs)
      br=$(git -C "$name" rev-parse --abbrev-ref HEAD)
      echo "| $name | $url | \`$sha\` | $d | $br |"
    else
      echo "| $name | $url | CLONE FAILED | | |"
    fi
  done
} > PINS.md
cat PINS.md
