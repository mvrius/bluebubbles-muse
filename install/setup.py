#!/usr/bin/env python3
"""setup.py — interactive installer for the bluebubbles-muse channel connector.

Run from the repo root:  python3 install/setup.py
or directly:              python3 install/setup.py

Prompts for every per-user value, writes ~/hooks/bluebubbles-channel.conf
(mode 600), installs the poll scripts, and renders the worker prompt template
(references/worker-prompt.md) into ~/hooks/bluebubbles-channel.prompt.md.

Stdlib only. Secrets are never echoed or logged.
"""

import getpass
import ipaddress
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

REPO_DIR = Path(__file__).resolve().parent.parent
HOOKS_DIR = Path.home() / "hooks"
SCRIPTS_DIR = HOOKS_DIR / "scripts"
CONF = HOOKS_DIR / "bluebubbles-channel.conf"
PROMPT_OUT = HOOKS_DIR / "bluebubbles-channel.prompt.md"

DEFAULT_SENDER_POLICY = (
    "Other allowlisted senders may chat and task the agent, but check with the "
    "owner before high-stakes actions, sensitive disclosures, automation changes, "
    "or third-party messages."
)
DEFAULT_RELAY_DEFAULTS = (
    "When asked to message someone reachable in an allowlisted group chat, default "
    "to relaying there in the third person; use a 1:1 chat only when explicitly requested."
)


def prompt(text, *, default=None, secret=False, required=False):
    """Prompt once (re-prompting only for required values left empty)."""
    label = f"{text}\n  [default: {default}]\n> " if default else f"{text}: "
    read = getpass.getpass if secret else input
    while True:
        try:
            val = read(label).strip()
        except EOFError:
            print("\nAborted.")
            sys.exit(1)
        if val:
            return val
        if default is not None:
            return default
        if not required:
            return ""
        print("A value is required here.", file=sys.stderr)


def url_looks_tailnet(url):
    """True if the URL points at a non-public address: tailnet, RFC1918,
    or CGNAT (100.64.0.0/10, where Tailscale lives). http only."""
    try:
        parts = urlparse(url)
        host = parts.hostname or ""
    except Exception:
        return False
    if parts.scheme != "http":
        return False
    if host.endswith(".ts.net"):
        return True
    try:
        # is_private is False for 100.64.0.0/10 (shared address space), so
        # check non-routability instead of privateness.
        return not ipaddress.ip_address(host).is_global
    except ValueError:
        return False


def preflight_tailnet():
    """Warn if Tailscale doesn't look usable on this host. Non-fatal."""
    if shutil.which("tailscale") is None:
        print("WARNING: `tailscale` CLI not found on this host — skipping tailnet check.")
        return
    try:
        r = subprocess.run(["tailscale", "status"], capture_output=True,
                           text=True, timeout=15)
    except Exception as e:
        print(f"WARNING: couldn't run `tailscale status` ({e}) — skipping tailnet check.")
        return
    if r.returncode != 0:
        print("WARNING: `tailscale status` failed — is Tailscale up and logged in on this host?")
        err = (r.stderr or r.stdout or "").strip().splitlines()
        if err:
            print("  " + err[0][:200])


def check_server(bb_url, bb_password):
    """Ping the BlueBubbles server the same way the poll driver reaches it."""
    https_proxy = os.environ.get("HTTPS_PROXY", "")
    base = https_proxy.rsplit(":", 1)[0] if ":" in https_proxy else https_proxy
    handlers = []
    if base:
        proxy_url = base + ":3130"
        handlers.append(urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url}))
    opener = urllib.request.build_opener(*handlers)
    url = (bb_url.rstrip("/") + "/api/v1/ping?password="
           + urllib.parse.quote(bb_password, safe=""))
    try:
        with opener.open(url, timeout=10) as resp:
            return json.load(resp).get("data") == "pong"
    except Exception:
        return False


def main():
    print("=== bluebubbles-muse setup ===")
    print(f"Values go straight into {CONF} (mode 600). Nothing is echoed back.\n")

    preflight_tailnet()
    print()

    bb_url = prompt("Mac tailnet URL (e.g. http://100.64.1.2:1234)", required=True)
    if not url_looks_tailnet(bb_url):
        print(f"WARNING: {bb_url!r} doesn't look like a tailnet/private address.")
        print("The BlueBubbles server must stay tailnet-only. "
              "Continue only if you know what you're doing.")
        if prompt("Continue anyway? [y/N]").lower() != "y":
            print("Aborted.")
            return 1

    bb_password = prompt("BlueBubbles server password", secret=True, required=True)

    print("Pinging the server the same way the poll driver will reach it...")
    if check_server(bb_url, bb_password):
        print("Server reachable.\n")
    else:
        print(f"WARNING: no pong from {bb_url} — is BlueBubbles running and the Mac awake?")
        if prompt("Continue anyway? [y/N]").lower() != "y":
            print("Aborted.")
            return 1
        print()

    bb_allowlist = prompt(
        "Allowlisted sender handles, comma-separated (e.g. +15551234567)",
        required=True,
    )
    if not bb_allowlist:
        print("Allowlist can't be empty — unknown senders are dropped by design.",
              file=sys.stderr)
        return 1
    bb_group_guids = prompt("Group chat GUIDs, comma-separated (optional, Enter to skip)")
    owner_name = prompt("Owner name (e.g. Jane Appleseed)", required=True)
    owner_handle = prompt("Owner handle (e.g. +15551234567)", required=True)
    sender_policy = prompt(
        "Per-sender latitude — who else is allowlisted and what each may ask for",
        default=DEFAULT_SENDER_POLICY,
    )
    relay_defaults = prompt(
        "Relay defaults — which chat to prefer when relaying to someone",
        default=DEFAULT_RELAY_DEFAULTS,
    )
    poll_interval = prompt("Poll interval seconds", default="5")

    (HOOKS_DIR / "state").mkdir(parents=True, exist_ok=True)
    SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)

    # --- config (600) ---
    old_umask = os.umask(0o077)
    try:
        CONF.write_text(
            "# bluebubbles-channel — generated by install/setup.py. Do not commit.\n"
            f"BB_URL={shlex.quote(bb_url)}\n"
            f"BB_PASSWORD={shlex.quote(bb_password)}\n"
            f"BB_ALLOWLIST={shlex.quote(bb_allowlist)}\n"
            f"BB_GROUP_GUIDS={shlex.quote(bb_group_guids)}\n"
        )
    finally:
        os.umask(old_umask)
    CONF.chmod(0o600)

    # --- scripts ---
    for name in ("bluebubbles-channel.sh", "bluebubbles-channel.py"):
        shutil.copy2(REPO_DIR / "scripts" / name, SCRIPTS_DIR / name)
    (SCRIPTS_DIR / "bluebubbles-channel.sh").chmod(0o755)

    # --- render worker prompt ---
    template = (REPO_DIR / "references" / "worker-prompt.md").read_text()
    values = {
        "owner_name": owner_name,
        "owner_handle": owner_handle,
        "sender_policy": sender_policy,
        "relay_defaults": relay_defaults,
    }
    rendered = template
    for key, val in values.items():
        rendered = rendered.replace("{{" + key + "}}", val)
    leftovers = sorted(set(re.findall(r"{{[a-z_]+}}", rendered)))
    if leftovers:
        print(f"ERROR: unrendered placeholders remain in {PROMPT_OUT}: "
              f"{', '.join(leftovers)}", file=sys.stderr)
        return 1
    PROMPT_OUT.write_text(rendered)

    mode = oct(CONF.stat().st_mode & 0o777)
    print("\n=== done ===")
    print(f"config:  {CONF} ({mode})")
    print(f"scripts: {SCRIPTS_DIR}/bluebubbles-channel.{{sh,py}}")
    print(f"prompt:  {PROMPT_OUT}")
    print("\n--- hook registration summary (for the agent) ---")
    print("id:                bluebubbles-channel")
    print(f"script_path:       {SCRIPTS_DIR}/bluebubbles-channel.sh")
    print(f"prompt:            contents of {PROMPT_OUT}")
    print(f"poll_interval_secs: {poll_interval}")
    print(f"allowlist:         {bb_allowlist}")
    print("-------------------------------------------------")
    print("Next: register the hook in your runtime, then run the smoke test "
          "in install/INSTALL.md step 5.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
