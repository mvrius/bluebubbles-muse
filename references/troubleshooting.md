# Troubleshooting

## No reply to a text

1. Is the Mac awake? (BlueBubbles "Keep macOS Awake" toggle, system energy settings.)
2. Is the BlueBubbles app running on the Mac?
3. Is Tailscale connected on the Mac, on the right tailnet?
4. Check the hook logs for `fetch-failed` (network/auth) vs `no-match` (filter dropped it).

## Replies work but inbound doesn't

The allowlist handle must match the sender address **exactly** as the server reports it (`+1...` vs email form). Query `POST /api/v1/message/query` and compare `handle.address` against `BB_ALLOWLIST`. This is the most common install bug.

## Everything worked, then stopped

- macOS update? BlueBubbles is unofficial — verify the app still runs and still has Full Disk Access (System Settings → Privacy & Security).
- Server password changed in the app? Update `~/hooks/bluebubbles-channel.conf` (mode stays 600).
- Mac got a new tailnet IP? Update `BB_URL`.

## Duplicate replies

The watermark (`~/hooks/state/bluebubbles-channel.last`) isn't advancing — check the state file is writable. Delete it to force a full rescan (old messages won't re-wake: only messages newer than the poll window with no watermark match... actually deleting the watermark means *everything* in the query window is "new" — expect one wake for the latest allowlisted message, then it settles).

## Testing safely

Run the poll script with `HATCH_HOOK_DRY_RUN=1` — it uses the `.dry` state file, so tests never move the real watermark or wake anyone.

## Disable

Tell the agent "disable the bluebubbles channel", or set `"enabled": false` in the hook definition.
