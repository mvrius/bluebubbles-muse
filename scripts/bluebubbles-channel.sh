#!/usr/bin/env bash
# bluebubbles-channel — hook entrypoint.
#
# Bash because log/silent/wake are bash functions from the hook runtime;
# this file sources the runtime and maps the Python driver's directives onto it.
# Everything else — config, fetch, filtering, watermark — lives in
# bluebubbles-channel.py, which prints:
#   LOG <event> <details-json>   -> log "<event>" '<details-json>'
#   WAKE                         -> wake "<reason>" '<payload-json>'  (next two lines)
#   SILENT                       -> silent "<reason>" '{}'            (next line)
set -euo pipefail
source "$HATCH_HOOK_RUNTIME"

STATE="$HOME/hooks/state/bluebubbles-channel.last"
if [[ "${HATCH_HOOK_DRY_RUN:-0}" == "1" ]]; then
  STATE="$STATE.dry"
fi

out="$(python3 "$HOME/hooks/scripts/bluebubbles-channel.py" \
  "$STATE" "$HOME/hooks/bluebubbles-channel.conf")" || {
  log "driver-failed" '{"error":"bluebubbles-channel.py exited nonzero"}'
  silent "driver failed" '{}'
  exit 0
}

while IFS= read -r line; do
  case "$line" in
    LOG\ *)
      rest="${line#LOG }"
      log "${rest%% *}" "${rest#* }"
      ;;
    WAKE)
      IFS= read -r reason
      IFS= read -r payload
      wake "$reason" "$payload"
      ;;
    SILENT)
      IFS= read -r reason
      silent "$reason" '{}'
      ;;
  esac
done <<< "$out"
