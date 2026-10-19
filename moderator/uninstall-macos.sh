#!/bin/bash
# Stops the ADA Ratings AI moderator and removes its LaunchAgent.
# The settings file (~/.config/ada-ratings/moderator.env) and the logs are kept.
set -euo pipefail

LABEL="net.adaratings.moderator"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$PLIST"
echo "Removed $LABEL."
echo "Kept $HOME/.config/ada-ratings/moderator.env and the logs in $HOME/Library/Logs; delete them by hand if you like."
