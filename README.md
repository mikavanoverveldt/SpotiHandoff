# SpotiHandoff

Tap an NFC tag and the music playing on your phone moves to the HEOS group, at the same
position — Apple's tap-to-handoff, built from Spotify Connect + Tasker. No server, no
daemon: at tap time everything runs on the phone. Two known limits: **the screen must be
on and unlocked** on stock Android, and `Woonkamer` must be listed in Spotify's device
list (a HEOS group that has been asleep for a long time may not be — see Troubleshooting).

Files: `get_token.py` (run once on a laptop) and this README.

## 1. Spotify dashboard

1. Go to <https://developer.spotify.com/dashboard>, log in, **Create app**.
2. Name/description anything. Under **Redirect URIs** add exactly:
   `http://127.0.0.1:8888/callback` — Spotify only allows plain `http` for loopback IPs,
   which is why the token is minted on the laptop.
3. Save. Keep the app in **Development mode** and add your own Spotify account under
   **User Management** (allowlist). Development mode is fine for one user.
4. Note the **Client ID** on the app page. There is no client secret involved — PKCE.

## 2. Mint the refresh token

On the laptop, with Python 3 only (no packages):

```sh
python3 get_token.py <your-client-id>
```

It opens your browser, you approve the two playback scopes, and the terminal prints a
refresh token. In Tasker, open **Variables** and add two globals:

| Name | Value |
|---|---|
| `%SPOT_CLIENT_ID` | the client id from the dashboard |
| `%SPOT_REFRESH` | the refresh token printed by the script |

The refresh token lasts **6 months from authorisation** (Spotify's policy since
2026; refreshing it does not extend the window). After that the token endpoint answers
`400 invalid_grant` and the task must be re-authorized: re-run `get_token.py` and paste
the new value into `%SPOT_REFRESH`. Set a calendar reminder for ~5 months out. The token
is also revoked if you change your Spotify password or remove the app.

## 3. Build the Tasker task

Create a task named **Spotify → Woonkamer** with these 7 actions, in this order. The
order matters: **every HTTP Request overwrites `%http_data`**, so the access token is
saved into its own variable before the second call.

| # | Action | Configuration |
|---|--------|---------------|
| 1 | HTTP Request (POST) | URL `https://accounts.spotify.com/api/token`; header `Content-Type: application/x-www-form-urlencoded`; body `grant_type=refresh_token&refresh_token=%SPOT_REFRESH&client_id=%SPOT_CLIENT_ID`; timeout 10; **Structure Output ON** |
| 2 | Variable Set | `%access` = `%http_data.access_token` |
| 3 | HTTP Request (GET) | URL `https://api.spotify.com/v1/me/player/devices`; header `Authorization: Bearer %access`; **Structure Output ON** |
| 4 | JavaScriptlet | `const d = JSON.parse(http_data).devices.find(x => x.name.toLowerCase() === 'woonkamer');`<br>`setLocal('devid', d ? d.id : '');` |
| 5 | If | `%devid` not set → Flash `Woonkamer not found` → Stop |
| 6 | HTTP Request (PUT) | URL `https://api.spotify.com/v1/me/player`; headers `Authorization: Bearer %access` and `Content-Type: application/json`; body `{"device_ids":["%devid"],"play":true}` |
| 7 | Flash | `%http_response_code` |

Notes:

- The device name is matched **case-insensitively but exactly** — no substring matching,
  because a HEOS AVR can expose several zones with similar names.
- The device id is **never hardcoded**: HEOS ids change after firmware reboots, so it is
  looked up on every tap.
- In action 5, use the If condition `%devid` *Is Not Set* (in Tasker: `%devid` matches
  nothing / `Is Set` unchecked). The Stop action goes inside that If.
- If your Tasker version has no *Structure Output* checkbox, turn it off and do both
  `JSON.parse` calls inside the single JavaScriptlet instead (the URL `%http_data` after
  the GET already contains the device list; do the token POST body parse as well).

**Test before wiring the tag:** play music on the phone, then run the task manually from
Tasker (the ▶ button). `204` means success. Nothing else in this project can be debugged
as cheaply as that response code.

## 4. NFC tag

1. Tasker → **Profiles** → **+** → **Event** → **NFC Tag**. Set **Tag ID** to your tag's
   id (tap **Scan Tag**), leave the content fields blank, and link the task above.
2. Write any plain-text record to the tag (e.g. Tasker's **NFC → Write Tag** action), or
   disable Android's system *Tags* app — otherwise every tap shows a "Tags / Tasker"
   chooser instead of firing the task directly.
3. Exempt Tasker from battery optimisation (Android Settings → Apps → Tasker → Battery →
   Unrestricted), or the HTTP request can be delayed at tap time.
4. NFC reads only with the **screen on and unlocked** on stock Android. There is no
   non-root workaround; expect to unlock the phone before tapping.

## Troubleshooting

Run the task manually from Tasker (▶) while music plays on the phone, then read the
final Flash: it is `%http_response_code` from the last HTTP Request. Add a temporary
`Flash %http_data` action before the end when you need Spotify's error body — remember
each request overwrites `%http_data`, so check it right after the call you care about.

| Symptom | Likely cause | Fix |
|---|---|---|
| `204` | Worked: the music moved to Woonkamer at the same position. | Nothing to do. |
| `400`/`401` about 6 months after setup | Refresh token expired. The token POST itself gets `400 invalid_grant`, but the final Flash usually shows `401` from the PUT with an empty token. | Re-run `get_token.py` and update `%SPOT_REFRESH` (see *Re-authorising* below). |
| `401` | Refresh token revoked (password change, app removed), client id typo, or `%SPOT_REFRESH` copied with a trailing space/newline. | Re-copy both globals from the dashboard and the script output; then re-authorise if it persists. |
| `400`/`401` right after changing phones or Tasker variables | The variable editor added a line break or stripped characters. | Delete and re-paste `%SPOT_REFRESH`; compare its length with the printed value. |
| `403` | Account is not Premium, the app owner's Premium lapsed, your account is not on the app's allowlist, or the scopes were not granted. | Check premium, add yourself under *User Management*, re-run `get_token.py` and approve both playback scopes. |
| `404` | The device id went stale or the group went offline between the two calls; or nothing is playing anywhere. | Start something on the phone and tap again. The id is looked up per tap, so a firmware reboot needs no fix. |
| `429` | Rate limit, or development-mode quota used up (quota is shared per developer account). | Wait a minute and retry; normal tap frequency is nowhere near the limit. |
| Flash `Woonkamer not found` | Group renamed, group split into separate HEOS zones, or the group is asleep and absent from `/me/player/devices`. | Check the exact name in Spotify's device picker (the match is exact, case-insensitive). Wake the group via HEOS, then retry. This is the known reliability limit. |
| Nothing happens on tap | Screen locked, NFC off, the Android *Tags* app is intercepting, Tasker's profile is disabled, or the tag fires a different profile. | Unlock, enable NFC, disable *Tags*/*Tags* chooser, re-scan the Tag ID in the profile, check Tasker is running. |
| No Flash at all, or it appears seconds late | Tasker is battery-optimised or has no data; Tasker itself is disabled; or action 5 stopped the task (then you see *Woonkamer not found* instead). | Exempt Tasker from battery optimisation, turn on mobile/wifi data, check the task wasn't stopped early. |
| Music jumps back to the phone | Spotify on the phone reclaimed playback (e.g. you pressed play there, or tapped the phone in Spotify's device picker). | Tap the tag again after starting playback; the phone must not be the active device when you tap. |
| Worked for months, suddenly not | Likely token expiry, Premium lapse, or a rename in HEOS. | Work down this table: token first, then Premium/allowlist, then the device name. |

### Re-authorising

1. On the laptop: `python3 get_token.py <your-client-id>`.
2. Approve both scopes and copy the new refresh token.
3. In Tasker → Variables, replace `%SPOT_REFRESH`; leave `%SPOT_CLIENT_ID` alone.
4. Run the task manually once; expect `204`. No tag changes needed.

Nothing here needs a server. If the idle-group check above proves unreliable, the fix
would be a helper process, which is explicitly out of scope for this project.
