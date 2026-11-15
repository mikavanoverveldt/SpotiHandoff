# SpotiHandoff — implementation brief

Recreate Apple's tap-to-handoff with Spotify + NFC: tapping a tag on the phone moves the
currently playing Spotify session onto the HEOS group, instead of the phone.

## Hard constraints

- **No server.** No Raspberry Pi, no NAS, no Home Assistant, no Docker, no always-on host.
  Everything at tap time runs on the Android phone in Tasker.
- The laptop is used **once** to mint a Spotify refresh token, then never again.
- No Python/Node dependencies. Stdlib only.
- No new abstractions, config files, or daemons. Two deliverables total.

## Verified background

- The HEOS setup is a single connected group: soundbar + subwoofer + 2 speakers, and it
  appears in Spotify as one Connect device named **`Woonkamer`**. HEOS devices are Spotify
  Connect endpoints, so "handoff" is one Web API call: `PUT /me/player` with the group's
  device id (`play: true`). Spotify keeps the position.
- Requires Spotify **Premium** and scopes `user-read-playback-state user-modify-playback-state`.
- Spotify only allows plain-`http` redirect URIs for **loopback IP literals**
  (`http://127.0.0.1:8888/callback`), which is why the token is minted on the laptop.
- PKCE means no client secret is needed anywhere — correct, since a secret stored in Tasker
  would be extractable.
- Tasker's `Event → NFC Tag` profile can fire a task on tap.
- Refresh tokens do not expire (revoked only by password change / app removal).

## Deliverables

```
get_token.py    # one-off: PKCE flow, prints a refresh token
README.md       # setup + the exact Tasker actions + troubleshooting
```

Do **not** create anything else.

### `get_token.py`

Usage: `python3 get_token.py <client_id>`

- `code_verifier = secrets.token_urlsafe(64)`; `code_challenge` = base64url of
  `sha256(verifier)` with `=` padding stripped.
- `webbrowser.open()` the authorize URL:
  `https://accounts.spotify.com/authorize` with `response_type=code`,
  `client_id`, `redirect_uri=http://127.0.0.1:8888/callback`, the two scopes,
  `code_challenge`, `code_challenge_method=S256`.
- Run a one-shot `http.server` on `127.0.0.1:8888`, take the first request to
  `/callback`, read `?code=` (and print the error if `?error=` came back instead).
- Exchange at `https://accounts.spotify.com/api/token` with `grant_type=authorization_code`,
  `code`, `redirect_uri`, `client_id`, `code_verifier` (no secret).
- Print the `refresh_token` clearly, plus a reminder to paste it and the client id into
  Tasker as `%SPOT_REFRESH` and `%SPOT_CLIENT_ID`.
- No `state` parameter: single-user, one-shot, loopback-only. Add a one-line comment saying so.

Aim for ~30–40 lines. One small self-check is enough (e.g. assert the challenge is
43 chars of base64url) — do not build a test suite for a script that runs once.

### Tasker task (`Spotify → Woonkamer`) — 7 actions

Exact order matters, because **every HTTP Request overwrites `%http_data`**. Save the
access token to its own variable in step 2 or steps 5–6 will read device data instead.

| # | Action | Configuration |
|---|--------|---------------|
| 1 | HTTP Request POST | URL `https://accounts.spotify.com/api/token`; header `Content-Type: application/x-www-form-urlencoded`; body `grant_type=refresh_token&refresh_token=%SPOT_REFRESH&client_id=%SPOT_CLIENT_ID`; timeout 10; **Structure Output ON** |
| 2 | Variable Set | `%access` = `%http_data.access_token` |
| 3 | HTTP Request GET | URL `https://api.spotify.com/v1/me/player/devices`; header `Authorization: Bearer %access`; **Structure Output ON** |
| 4 | JavaScriptlet | `const d = JSON.parse(http_data).devices.find(x => x.name.toLowerCase() === 'woonkamer');`<br>`setLocal('devid', d ? d.id : '');` |
| 5 | If | `%devid` not set → Flash `Woonkamer not found` → Stop |
| 6 | HTTP Request PUT | URL `https://api.spotify.com/v1/me/player`; headers `Authorization: Bearer %access` and `Content-Type: application/json`; body `{"device_ids":["%devid"],"play":true}` |
| 7 | Flash | `%http_response_code` |

Notes for whoever implements this in the README:

- Match the device **case-insensitively but exactly**. No substring matching — a HEOS AVR
  can expose several zones with similar names.
- Never hardcode the device id: HEOS ids change after firmware reboots. Look it up per tap.
- If the phone's Tasker lacks the *Structure Output* checkbox, do the JSON parsing for both
  calls inside the single JavaScriptlet using `%http_data` instead; the rest is unchanged.

### NFC setup (README steps, no code)

1. `Event → NFC Tag`, matched by **Tag ID**, content blank → run the task above.
2. Write any plain text record to the tag (Tasker's own `NFC → Write Tag` action works), or
   disable the system *Tags* app — otherwise Android shows a "Tags / Tasker" chooser on every tap.
3. Exempt Tasker from battery optimisation, or the HTTP request can be delayed.
4. NFC only reads with the **screen on and unlocked** on stock Android. Say so plainly in the
   README; there is no workaround without root.

## README structure

1. What it does, one paragraph, and the two limitations (unlocked screen; HEOS must be
   listed in Spotify's device list).
2. Spotify dashboard: create app, add redirect URI `http://127.0.0.1:8888/callback`, keep it
   in dev mode with your own account on the user allowlist (fine for one user).
3. Run `get_token.py`, paste `%SPOT_CLIENT_ID` and `%SPOT_REFRESH` into Tasker's Variables tab.
4. Build the 7-action task (table above), then **run it manually from Tasker** before wiring
   the tag — a response code is the debug loop.
5. NFC profile + tag writing.
6. Troubleshooting table:
   - `204` — worked; music moved to Woonkamer.
   - `401` — wrong/revoked refresh token, or wrong client id.
   - `403` — not Premium, account not on the allowlist, or scopes missing.
   - `404` — device id stale or the group went offline between the two calls.
   - `Woonkamer not found` — group renamed, or asleep and absent from the device list.
   - Nothing at all — screen locked, NFC off, or the system Tags app intercepting the tap.

## Verification before declaring done

- Script runs end to end against a real Spotify account and prints a refresh token.
- Task run manually from Tasker while music plays on the phone returns `204` and the audio
  moves to the group at the same position.
- Task run while the group has been idle for a while: record honestly whether `Woonkamer`
  was listed. This is the one unknown that decides whether the approach is reliable.

## Out of scope — do not build

Reverse tag (hand back to the phone), volume presets, retry/backoff, logging, HEOS local API
(port 1255) wake-up, a web UI, a server, persistence beyond the two Tasker globals.

If the idle-device check fails, report it and stop; the fix would be a helper process, which
the user has explicitly ruled out.
