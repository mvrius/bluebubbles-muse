# BlueBubbles API surface used by this connector

Base: `$BB_URL`, auth via `?password=$BB_PASSWORD` query parameter on every call. All JSON.

## `GET /api/v1/ping`

Connectivity + auth check. → `{"status":200,"data":"pong"}`

## `POST /api/v1/message/query`

Recent messages. Body:

```json
{"limit":20,"offset":0,"with":["handle","chat"],"sort":"DESC"}
```

Useful fields per message: `isFromMe`, `text`, `handle.address`, `chats[0].guid`, `chats[0].participants[]`, `dateCreated` (ms epoch), `guid`.

## `POST /api/v1/chat/query`

Chats. Body: `{"limit":50}` (raise to 200 when resolving an unknown chatGuid). Fields: `guid`, `displayName`, `participants[].address`. Group chats have 2+ participants. Used at install to discover group GUIDs, and by the worker to resolve a chatGuid for a 1:1 reply.

## `POST /api/v1/message/text`

Send a text. Body:

```json
{"chatGuid":"...","message":"...","tempGuid":"temp-<unique>"}
```

→ `{"status":200,"message":"Message sent!"}`. `tempGuid` must be unique per send; `temp-$(date +%s%N)` works.

## Attachments

Include `"attachment"` in the message query's `with` array to list them: `guid`, `mimeType`, `transferName`, `totalBytes`.

- `GET /api/v1/attachment/<guid>` → attachment **metadata** JSON.
- `GET /api/v1/attachment/<guid>/download` → the file bytes. The server may transcode (e.g. HEIC→JPEG).

## Chat GUID shapes

Seen in the wild: 1:1 → `any;-;<handle>` (also `iMessage;-;<handle>` on some objects); group → `<service>;+;<id>`. Always prefer the guid exactly as returned by the API; never construct one.
