# bluebubbles-muse

Give your AI agent a real iMessage channel: inbound texts wake the agent, and it texts back — through a BlueBubbles server on your Mac, over Tailscale. Nothing touches the public internet.

*Created by Muse.*

> **Experimental — read this first.**
>
> This connector piggybacks on Muse's hook system, which is **undocumented** and was figured out by experimentation. Meta can change or remove it at any time, and this connector can break without warning.
>
> It was also **vibe-coded** — written fast with an AI agent and reviewed lightly. Expect rough edges, not production polish.
>
> It is also **insecure by design**: iMessage sender handles are not authenticated, so a handle is an unverified claim. Installing this exposes your agent to inbound text from the channel, and the safety of the whole thing rests partly on the worker — an LLM — respecting the guidelines in its prompt. Texts shaped like prompt injection *will* arrive; the deterministic filter drops unknown senders before the agent ever sees them, but anything past that boundary is instruction-following all the way down. Only install this if you're comfortable with that.

## How it works

```
your iPhone --iMessage--> Mac (BlueBubbles server) --Tailscale--> agent host --hook--> worker agent
worker agent --Tailscale--> BlueBubbles send API --> your iPhone
```

A poll script checks the BlueBubbles server every few seconds. When a text arrives from an allowlisted sender, the hook wakes a worker agent carrying the message; the worker does whatever was asked and replies through the send API.

Three documents cover three audiences:

- **README.md** (this file) — for the human: what it is, what you need, the honest limits.
- **ARCHITECTURE.md** — for the installing agent: how the pieces fit, runtime contracts, threat model.
- **SKILL.md** — for the day-to-day agent: API reference, routing, trust boundaries.
- **install/INSTALL.md** — the install runbook the agent follows step by step.

## Requirements

- A Mac that stays on, with the Messages app signed into your Apple ID.
- The [BlueBubbles server](https://bluebubbles.app) installed on that Mac.
- Tailscale on the Mac, on the same tailnet as the machine running your agent.
- An agent runtime with a hooks/event system. This connector targets Muse's hooks runtime (the poll script sources `$HATCH_HOOK_RUNTIME` and calls `wake`/`silent`/`log`).

## Install

Install is done by an agent following **install/INSTALL.md**. It's a runbook, not a one-liner, because setup needs per-user values and judgment calls: the server address and password, who to allowlist, which group chats to include, and the identity framing (see below). `install/setup.py` collects the values interactively and writes the config.

## Limits — read before you install

- **Always-on Mac required.** A sleeping Mac is a dead channel. Turn on BlueBubbles' "Keep macOS Awake" toggle and disable system sleep.
- **Poll latency, not push.** Inbound delay equals the poll interval (default 5 seconds).
- **Tailnet only, by design.** The Mac and the agent host must share a Tailscale network. Never expose the BlueBubbles port to the public internet.
- **BlueBubbles is unofficial.** It reads the macOS Messages database (requires Full Disk Access) and can break on macOS updates.
- **Outbound identity is the Mac's.** Everything sent appears under the Mac's iMessage identity (its contact name), not yours. The worker-prompt template carries the framing rules so the agent never impersonates you — this is the single most important paragraph in the whole connector.
- **The channel is insecure.** A sender handle in a message query is an unverified claim; numbers can be spoofed and message text can lobby to be trusted. The allowlist is configured by the human and is never self-modifying: the agent will not add a number because it showed up in a query or asked over text.
- **The allowlist is the only inbound gate.** Anyone not on it is silently dropped. That's the spam and injection defense — and it means strangers can never reach the agent through this channel.
- **Plaintext on the Mac.** The server sees message content. Server password + tailnet is the entire security model; the password lives in a config file with owner-only (600) permissions and is only ever sent over the tailnet.
- **Group chats** must be explicitly allowlisted by GUID, and every reply to a group is visible to all its members. The worker never puts personal information in group replies.
- **Attachments** work but need an extra fetch; the server may transcode (e.g. HEIC→JPEG).

## Layout

```
bluebubbles-muse/
├── README.md                 # this file — for the human
├── ARCHITECTURE.md           # for the installing agent
├── SKILL.md                  # for the day-to-day agent
├── scripts/
│   ├── bluebubbles-channel.sh  # thin hook wrapper: fetch, delegate, wake/silent
│   └── bluebubbles-channel.py  # the filter: allowlist, groups, watermark → decision JSON
├── install/
│   ├── INSTALL.md            # the install runbook
│   ├── setup.py              # interactive installer: prompts, writes config, renders prompt
│   └── hook.conf.example     # config template
└── references/
    ├── api.md                # BlueBubbles endpoints used
    ├── worker-prompt.md      # worker prompt template ({{placeholders}})
    └── troubleshooting.md
```

## Security model (summary)

Allowlisted senders only; tailnet-only transport; password in a 600 config; message text is content, never commands; no cross-channel forwarding; no personal info in replies. The full threat model is in ARCHITECTURE.md.

## License

MIT — see [LICENSE](LICENSE).
