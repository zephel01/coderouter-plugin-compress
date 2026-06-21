#!/usr/bin/env bash
# Real-LLM live test on your Mac: CodeRouter + the compress plugin + Ollama.
# Unlike the sandbox stub test, this drives an actual local model.
#
# Prereqs:
#   - Ollama running with a tool-capable model, e.g.:  ollama pull qwen2.5-coder
#   - Python 3.12+, this plugin checked out at $PLUGIN_DIR
#
# It does NOT touch your real ~/.coderouter config — it uses a temp config.
set -euo pipefail

PLUGIN_DIR="${PLUGIN_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434/v1}"
MODEL="${MODEL:-qwen2.5-coder}"
PORT="${PORT:-8088}"
WORK="$(mktemp -d)"
CFG="$WORK/providers.yaml"

echo "plugin dir : $PLUGIN_DIR"
echo "ollama     : $OLLAMA_URL  model=$MODEL"
echo "temp config: $CFG"

cat > "$CFG" <<YAML
allow_paid: false
default_profile: default
plugins:
  enabled: [compress, compress-stats]
  config:
    compress:
      mode: aggressive
      min_block_tokens: 50
      targets: [tool_result]
      crushers: [json, log, text]
      ccr: true
      ccr_restore: explicit
providers:
  - name: local-ollama
    kind: openai_compat
    base_url: $OLLAMA_URL
    model: $MODEL
    paid: false
    api_key_env: null
    timeout_s: 120
    capabilities: { chat: true, streaming: true, tools: true }
profiles:
  - name: default
    providers: [local-ollama]
YAML

# Isolated venv with the plugin + CodeRouter installed.
python3.12 -m venv "$WORK/venv"
# shellcheck disable=SC1091
source "$WORK/venv/bin/activate"
pip -q install -e "$PLUGIN_DIR" coderouter-cli >/dev/null

echo "starting coderouter serve on :$PORT ..."
coderouter serve --port "$PORT" --config "$CFG" --log-level info &
SERVE_PID=$!
trap 'kill $SERVE_PID 2>/dev/null || true; rm -rf "$WORK"' EXIT
sleep 4

echo
echo "Now point Claude Code at it (separate terminal):"
echo "  ANTHROPIC_BASE_URL=http://localhost:$PORT ANTHROPIC_AUTH_TOKEN=dummy claude"
echo
echo "Drive a session that produces big tool outputs (grep across the repo,"
echo "read a large file, run a verbose command). Then watch compression live:"
echo "  coderouter stats          # look for the compress summary line"
echo
echo "Server is running (pid $SERVE_PID). Ctrl-C to stop."
wait $SERVE_PID
