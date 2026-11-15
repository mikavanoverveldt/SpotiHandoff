#!/usr/bin/env python3
"""One-off: mint a Spotify refresh token for the Tasker task.

Usage: python3 get_token.py <client_id>

The Spotify app's redirect URI must be exactly http://127.0.0.1:8888/callback
"""
import base64, hashlib, http.server, json, secrets, sys, urllib.error, urllib.parse, urllib.request, webbrowser

REDIRECT = "http://127.0.0.1:8888/callback"
SCOPES = "user-read-playback-state user-modify-playback-state"
result = {}


class Callback(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if "code" in query or "error" in query:
            result.update(query)
            body = b"Done. Go back to the terminal."
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def log_message(self, *args):
        pass


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    client_id = sys.argv[1]
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    assert len(challenge) == 43 and "=" not in challenge
    # No state parameter: single user, one-shot, loopback-only.
    webbrowser.open("https://accounts.spotify.com/authorize?" + urllib.parse.urlencode({
        "response_type": "code", "client_id": client_id, "redirect_uri": REDIRECT,
        "scope": SCOPES, "code_challenge": challenge, "code_challenge_method": "S256"}))
    with http.server.HTTPServer(("127.0.0.1", 8888), Callback) as httpd:
        while not result:  # ignores stray requests (e.g. /favicon.ico) until the callback
            httpd.handle_request()
    if "error" in result:
        sys.exit("Spotify returned an error: " + result["error"][0])
    request = urllib.request.Request("https://accounts.spotify.com/api/token", data=urllib.parse.urlencode({
        "grant_type": "authorization_code", "code": result["code"][0],
        "redirect_uri": REDIRECT, "client_id": client_id, "code_verifier": verifier}).encode())
    try:
        with urllib.request.urlopen(request) as response:
            tokens = json.load(response)
    except urllib.error.HTTPError as error:
        sys.exit("Token exchange failed: " + error.read().decode())
    print("\nRefresh token:\n\n  %s\n" % tokens["refresh_token"])
    print("Paste it into Tasker's Variables tab as %SPOT_REFRESH,")
    print("and the client id as %SPOT_CLIENT_ID (see README).")


if __name__ == "__main__":
    main()
