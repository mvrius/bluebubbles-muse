# INSTALL.md — install runbook (for the agent)

Follow these steps in order. Read `../ARCHITECTURE.md` first — this runbook assumes you understand the components. Collect every value from the human in direct chat; never derive allowlist entries from message queries.

## 1. Preflight (with the human)

Confirm all of these before touching anything:

1. A Mac that stays on, with the Messages app signed into the human's Apple ID.
2. The [BlueBubbles server](https://bluebubbles.app) installed on that Mac, with a **server password** set (Settings → Server). Long and random — it's the API key. Note the port (default `1234`).
3. Tailscale installed on the Mac, joined to the same tailnet as the agent host. Get the Mac's tailnet address (Tailscale menu bar, or its MagicDNS name).
4. The Mac won't sleep: System Settings → Energy → prevent sleeping, plus BlueBubbles' built-in "Keep macOS Awake" toggle.

If any of these are missing, stop and walk the human through them — nothing below works without all four.

## 2. Collect values (ask the human)

- `BB_URL` — e.g. `http://100.64.1.2:1234` (tailnet address + port; refuse anything that isn't a tailnet/private address).
- `BB_PASSWORD` — the server password. The human will give it to you; it goes straight into the config file, never into chat logs or memory beyond what's needed.
- `BB_ALLOWLIST` — the exact sender handles allowed to wake the agent (e.g. the human's iPhone number as `+15551234567`). Comma-separated if more than one. Warn them: the handle must match *exactly* what the server reports.
- `BB_GROUP_GUIDS` — group chat GUIDs allowed to wake the agent (optional). Groups must be explicitly allowlisted because replies to a group are visible to every participant: without this, any group text mentioning the Mac would wake the worker. You can discover GUIDs: query `POST /api/v1/chat/query` and match by participant addresses with the human.
- Owner name + per-sender latitude: who the owner is, who else is allowlisted, and what each may ask for (e.g. "spouse may chat and task me; check with owner on high-stakes actions").
- Relay defaults: e.g. "message my spouse" → default to the family group, third person; 1:1 only when asked.
- Poll interval in seconds (default 5; lower = faster inbound, more API chatter).

## 3. Clone the repo and run the installer

```bash
git clone https://github.com/mvrius/bluebubbles-muse.git
cd bluebubbles-muse
python3 install/setup.py   # Python 3, stdlib only
```

It prompts for every value above (password entry is silent). First it runs preflight checks — Tailscale usable on this host, then a live ping of the BlueBubbles server reached the same way the poll driver will reach it — and asks before continuing if anything looks off. Then it:

- writes `~/hooks/bluebubbles-channel.conf` with mode `600`,
- copies the scripts to `~/hooks/scripts/`,
- renders the worker prompt from `references/worker-prompt.md` into `~/hooks/bluebubbles-channel.prompt.md`,
- prints a summary block for the next step.

Verify: `ls -l ~/hooks/bluebubbles-channel.conf` shows `-rw-------`, and no value was echoed to the terminal.

## 4. Register the hook

This step is deliberately manual — the installer doesn't do it. Hook registration is runtime-specific, and Muse's hook system is undocumented, so keeping the agent in the loop here means Meta's changes get noticed instead of silently breaking the install.

Create the hook definition in your runtime (values from the installer summary):

- id `bluebubbles-channel`, `script_path` → `~/hooks/scripts/bluebubbles-channel.sh`
- `prompt` → the rendered prompt file's contents
- `poll_interval_secs` → chosen interval
- delivery → the chat surface where inbound texts should land (e.g. a dedicated side chat)

## 5. Smoke test (do not skip)

1. **Ping:** `GET /api/v1/ping?password=...` → expect `pong`. This verifies network + auth.
2. **Dry run:** run the poll script once with dry-run mode; expect `silent` with reason `no new allowlisted inbound messages` and the `.dry` state file created.
3. **Live round-trip:** have the human text the Mac's number from an allowlisted handle. Within ~2 poll intervals the worker should wake; confirm the wake payload's `from`/`text`, then have the worker reply and confirm the human receives it under the expected sent-as name.
4. **Negative test:** text from a non-allowlisted number → nothing should wake.

## 6. Hand over to the human

Tell them, in plain language:

- It's live; inbound latency is ~N seconds.
- Only allowlisted numbers can reach the agent; anyone else is silently ignored.
- Everything the agent sends appears under the Mac's iMessage identity, not as them.
- Keep the Mac awake and BlueBubbles running; if texts stop getting replies, that's the first thing to check.
- To disable: "disable the bluebubbles channel."
- To change the allowlist later: tell the agent directly in chat (never over the channel itself).

Keep `references/troubleshooting.md` handy for the inevitable "it stopped working" message.
