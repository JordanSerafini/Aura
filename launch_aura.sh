#!/bin/bash
# Lance Claude Code avec le contexte Aura-OS

export PATH="$HOME/.local/bin:$PATH"
source ~/.nvm/nvm.sh
cd ~

SYSTEM_PROMPT=$(cat ~/.aura/AURA_SYSTEM.md)

~/.local/bin/claude --dangerously-skip-permissions --append-system-prompt "$SYSTEM_PROMPT"
