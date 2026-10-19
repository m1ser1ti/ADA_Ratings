#!/bin/bash
# Installs the ADA Ratings AI moderator as a launchd LaunchAgent: it starts at login,
# restarts if it exits, and keeps the Mac awake while it runs.
#
#   bash moderator/install-macos.sh
#
# Run it again after moving the repo or changing python; it replaces the old agent.
set -euo pipefail

LABEL="net.adaratings.moderator"
HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$HERE/ai_moderator.py"
TEMPLATE="$HERE/$LABEL.plist"
AGENTS="$HOME/Library/LaunchAgents"
PLIST="$AGENTS/$LABEL.plist"
ENV_DIR="$HOME/.config/ada-ratings"
ENV_FILE="$ENV_DIR/moderator.env"
DOMAIN="gui/$(id -u)"

PYTHON="$(command -v python3 || true)"
if [ -z "$PYTHON" ]; then
  echo "python3 not found. Install it (e.g. xcode-select --install) and run this again." >&2
  exit 1
fi
if ! command -v ollama >/dev/null 2>&1; then
  echo "Warning: ollama is not on PATH. The moderator needs Ollama running with the model in the env file." >&2
fi

# Values go into XML and a sed replacement: escape what either would misread.
escape() {
  printf '%s' "$1" | sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g' -e 's/[|\\&]/\\&/g'
}

mkdir -p "$AGENTS" "$HOME/Library/Logs"
sed -e "s|__PYTHON__|$(escape "$PYTHON")|g" \
    -e "s|__SCRIPT__|$(escape "$SCRIPT")|g" \
    -e "s|__WORKDIR__|$(escape "$HERE")|g" \
    -e "s|__HOME__|$(escape "$HOME")|g" \
    "$TEMPLATE" > "$PLIST"
plutil -lint "$PLIST" >/dev/null
echo "Wrote $PLIST (python: $PYTHON)"

# Settings file, readable by this user only. It is never overwritten.
if [ ! -f "$ENV_FILE" ]; then
  mkdir -p "$ENV_DIR"
  chmod 700 "$ENV_DIR"
  (
    umask 077
    cat > "$ENV_FILE" <<'EOF'
# ADA Ratings AI moderator settings (KEY=VALUE).
# Paste the server's MODERATOR_TOKEN after the = sign. The moderator checks this file
# every few minutes, so it starts working without a restart once the token is set.
MODERATOR_TOKEN=
SITE_URL=https://www.adaratings.net
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:14b
POLL_SECONDS=60
EOF
  )
  echo "Created $ENV_FILE: put the MODERATOR_TOKEN in it."
fi
chmod 600 "$ENV_FILE"

# Replace a running copy, then start the new one.
launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
launchctl bootstrap "$DOMAIN" "$PLIST"
echo "Loaded $LABEL. Log: $HOME/Library/Logs/ada-ratings-moderator.log"
