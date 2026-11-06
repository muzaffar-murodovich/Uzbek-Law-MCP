#!/bin/zsh
# End-to-end check: ask Claude Code (headless) each question with only the Qonunshunos MCP
# server available, and keep the stream-json transcripts for scripts/e2e_analyze.py.
#   uv run qonunshunos serve &            # http://127.0.0.1:8000/mcp
#   scripts/e2e_claude.sh eval/e2e/questions.tsv data/e2e
# Runs count against the Claude plan of whoever runs them (≈0.1 USD-equivalent per question).
set -u
questions=${1:A}
out=${2:A}
url=${3:-http://127.0.0.1:8000/mcp}
mkdir -p $out/runs $out/work
print -r -- "{\"mcpServers\": {\"qonunshunos\": {\"type\": \"http\", \"url\": \"$url\"}}}" > $out/mcp.json
cd $out/work  # outside the repo, so no project CLAUDE.md leaks into the answers
while IFS=$'\t' read -r id q; do
  [[ -z $id || $id == \#* ]] && continue
  [[ -s $out/runs/$id.jsonl ]] && { echo "$id skip"; continue; }
  start=$(date +%s)
  # stdin from /dev/null: otherwise claude -p appends the rest of the questions file
  timeout 300 claude -p "$q" --mcp-config $out/mcp.json --strict-mcp-config --tools "" \
    --allowedTools "mcp__qonunshunos__*" --output-format stream-json --verbose \
    --no-session-persistence < /dev/null > $out/runs/$id.jsonl 2> $out/runs/$id.err
  echo "$id exit=$? $(( $(date +%s) - start ))s"
done < $questions
