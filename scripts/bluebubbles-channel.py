#!/usr/bin/env python3
"""BlueBubbles poll driver for the bluebubbles-channel hook.

Does everything the hook needs on each poll: reads the config, fetches the
latest messages from the BlueBubbles server (over the tailnet through the
runtime tunnel proxy), decides whether an allowlisted sender wrote something
new, and advances the watermark.

It prints directive lines for the thin bash shim:

    LOG <event> <details-json>     (zero or more)
    WAKE                           (then: reason line, payload JSON line)
    SILENT                         (then: reason line)

Trust boundaries enforced here, before any agent sees the payload:
  1. Sender allowlist -- anyone else's messages never wake, 1:1 or group.
  2. Chat allowlist -- 1:1 chats always eligible; a group chat only wakes if
     its guid is in the group list. Replies to a group are visible to ALL
     its members.
  3. Schema check -- text must be present and non-empty.

Usage:
    bluebubbles-channel.py <state_file> <conf_path>

Exit status is 0 on a clean run (even when silent); nonzero only on
unexpected failure, in which case the shim logs and silences.
"""
import json
import os
import re
import shlex
import sys
import urllib.parse
import urllib.request
from pathlib import Path


def log(event, details):
    print(f"LOG {event} {json.dumps(details, separators=(',', ':'))}")


def load_conf(path):
    """Parse a KEY=value conf file (values may be shlex-quoted). None if missing."""
    try:
        text = Path(path).read_text()
    except FileNotFoundError:
        return None
    conf = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"([A-Za-z_][A-Za-z0-9_]*)=(.*)", line)
        if not m:
            continue
        try:
            parts = shlex.split(m.group(2).strip())
            conf[m.group(1)] = parts[0] if parts else ""
        except ValueError:
            conf[m.group(1)] = m.group(2).strip().strip("'\"")
    return conf


def tunnel_proxy_url():
    """The runtime tunnel proxy derived from HTTPS_PROXY (TCP only)."""
    https_proxy = os.environ.get("HTTPS_PROXY", "")
    base = https_proxy.rsplit(":", 1)[0] if ":" in https_proxy else https_proxy
    return base + ":3130" if base else ""


def fetch_messages(bb_url, bb_password):
    body = json.dumps(
        {"limit": 20, "offset": 0, "with": ["handle", "chat"], "sort": "DESC"}
    ).encode()
    url = (
        bb_url.rstrip("/")
        + "/api/v1/message/query?password="
        + urllib.parse.quote(bb_password, safe="")
    )
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    handlers = []
    proxy = tunnel_proxy_url()
    if proxy:
        handlers.append(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        )
    opener = urllib.request.build_opener(*handlers)
    with opener.open(req, timeout=10) as resp:
        return json.load(resp)


def parse_watermark(path):
    try:
        with open(path) as f:
            parts = f.read().strip().split()
    except FileNotFoundError:
        return 0, ""
    last_dc = int(parts[0]) if parts and parts[0].isdigit() else 0
    last_guid = parts[1] if len(parts) > 1 else ""
    return last_dc, last_guid


def write_watermark(path, date_created, guid):
    with open(path, "w") as f:
        f.write(f"{date_created} {guid}")


def decide(messages, state_file, allowlist, group_guids):
    """Pure filter: message-query JSON -> (decision, reason, payload|None)."""
    last_dc, last_guid = parse_watermark(state_file)

    candidates = []
    for m in messages:
        if m.get("isFromMe"):
            continue
        text = m.get("text")
        if not text:
            continue
        dc = m.get("dateCreated") or 0
        guid = m.get("guid") or ""
        if dc <= last_dc and not (dc == last_dc and last_guid and guid != last_guid):
            continue
        sender = (m.get("handle") or {}).get("address") or ""
        if not sender or sender not in allowlist:
            continue
        chats = m.get("chats") or [{}]
        chat = chats[0] or {}
        chat_guid = chat.get("guid") or ""
        is_group = chat_guid in group_guids
        if not is_group and len(chat.get("participants") or []) > 1:
            continue
        candidates.append(
            {
                "sender": sender,
                "text": text,
                "dateCreated": dc,
                "guid": guid,
                "chatGuid": chat_guid,
                "isGroup": is_group,
            }
        )

    if not candidates:
        # Advance the watermark past everything seen so we don't re-evaluate it.
        newest_dc, newest_guid = 0, ""
        for m in messages:
            dc = m.get("dateCreated") or 0
            if dc > newest_dc:
                newest_dc, newest_guid = dc, m.get("guid") or ""
        write_watermark(state_file, newest_dc, newest_guid)
        return ("silent", "no new allowlisted inbound messages", None)

    best = max(candidates, key=lambda c: c["dateCreated"])
    write_watermark(state_file, best["dateCreated"], best["guid"])
    payload = {
        "channel": "bluebubbles",
        "from": best["sender"],
        "chatGuid": best["chatGuid"],
        "text": best["text"],
        "dateCreated": best["dateCreated"],
        "guid": best["guid"],
        "isGroup": best["isGroup"],
    }
    return ("wake", f"bluebubbles message from {best['sender']}", payload)


def main():
    state_file, conf_path = sys.argv[1], sys.argv[2]

    conf = load_conf(conf_path)
    if conf is None:
        log("missing-config", {"error": "bluebubbles-channel.conf not found"})
        print("SILENT\nnot configured")
        return 0

    bb_url = conf.get("BB_URL", "")
    bb_password = conf.get("BB_PASSWORD", "")
    allowlist = {a.strip() for a in conf.get("BB_ALLOWLIST", "").split(",") if a.strip()}
    group_guids = {g.strip() for g in conf.get("BB_GROUP_GUIDS", "").split(",") if g.strip()}
    if not bb_url or not bb_password or not allowlist or "<" in bb_url:
        log("missing-config", {"error": "BB_URL/BB_PASSWORD/BB_ALLOWLIST incomplete"})
        print("SILENT\nnot configured")
        return 0

    try:
        resp = fetch_messages(bb_url, bb_password)
    except Exception as e:
        log("fetch-failed", {"error": f"BlueBubbles API unreachable ({type(e).__name__})"})
        print("SILENT\nbluebubbles unreachable")
        return 0

    decision, reason, payload = decide(resp.get("data") or [], state_file, allowlist, group_guids)
    if decision == "wake":
        log("wake", {"from": payload["from"], "dateCreated": payload["dateCreated"]})
        print("WAKE")
        print(reason)
        print(json.dumps(payload, separators=(",", ":")))
    else:
        log("no-match", {"reason": reason})
        print("SILENT")
        print(reason)
    return 0


if __name__ == "__main__":
    sys.exit(main())
