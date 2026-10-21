#!/usr/bin/env bash
# Silent demo capture for the promo video: asciinema cast -> agg gif -> mp4.
#
# Types each command at human speed under a fake zsh prompt and runs the REAL
# CLI, so every line of output is genuine (recorded at 150x36 so the long
# detection paths render unwrapped on a 16:9 canvas). Rendered with:
#
#   env TERM=xterm-256color PATH="$PWD/venv/bin:$PATH" \
#     venv/bin/asciinema rec -c "bash promo/record_demo.sh" --cols 150 --rows 36 promo/demo.cast
#   agg --font-size 22 --fps-cap 30 promo/demo.cast promo/demo.gif
#   ffmpeg -i promo/demo.gif -vf "scale=1920:-2:flags=lanczos,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:0x0B0D11" \
#          -c:v libx264 -crf 18 -pix_fmt yuv420p -movflags +faststart promo/demo.mp4

GREEN=$'\033[1;32m'; CYAN=$'\033[1;36m'; YELLOW=$'\033[1;33m'
DIM=$'\033[2m'; RESET=$'\033[0m'

prompt() {
  printf '%s➜  %sdrupal-mcp-server %sgit:(main)%s %s✦%s ' \
    "$GREEN" "$CYAN" "$YELLOW" "$RESET" "$DIM" "$RESET"
}

typed() {
  local cmd="$1" i
  prompt
  for (( i=0; i<${#cmd}; i++ )); do
    printf '%s' "${cmd:$i:1}"
    sleep 0.05
  done
  printf '\n'
  eval "$cmd"   # actually run what was just typed, output lands in the cast
  sleep 0.2
}

typed 'drupal-mcp --version'
sleep 1.5
typed 'drupal-mcp install --list'
sleep 2.0
typed 'drupal-mcp install --print'
sleep 3.0
typed 'uvx --from drupal-mcp-server drupal-mcp --version'
sleep 4.0
prompt
