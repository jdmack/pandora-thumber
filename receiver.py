from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
from urllib import request, error

HOST = "0.0.0.0"
PORT = 8765
BATCH_FILE = Path(__file__).with_name("current_batch.txt")
BATCH_THRESHOLD = 28
NTFY_TOPIC = "wolfswatch-pandora-thumber"
NTFY_URL = f"https://ntfy.sh/{NTFY_TOPIC}"


def log(message=""):
    print(message, flush=True)


def load_existing_tracks():
    if not BATCH_FILE.exists():
        return set()

    return {
        line.strip()
        for line in BATCH_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


seen_tracks = load_existing_tracks()
# If we start while an old batch is already full, assume it has already fired.
# Deleting/clearing the batch file below the threshold automatically rearms it.
batch_full_triggered = len(seen_tracks) >= BATCH_THRESHOLD


def refresh_batch_state():
    global seen_tracks, batch_full_triggered

    seen_tracks = load_existing_tracks()

    if len(seen_tracks) < BATCH_THRESHOLD and batch_full_triggered:
        batch_full_triggered = False
        log("[Pandora Thumber] Batch is below threshold; full-batch trigger rearmed.")


def send_ntfy_notification():
    count = len(seen_tracks)
    body = f"Pandora batch is ready: {count} songs in current_batch.txt"

    req = request.Request(
        NTFY_URL,
        data=body.encode("utf-8"),
        method="POST",
        headers={
            "Title": "Pandora Thumber",
            "Priority": "default",
            "Tags": "musical_note",
        },
    )

    try:
        with request.urlopen(req, timeout=10) as response:
            response.read()
        log(f"[Pandora Thumber] ntfy alert sent: {count} tracks")
    except (error.URLError, TimeoutError, OSError) as exc:
        log(f"[Pandora Thumber] ntfy alert failed: {exc}")


def append_to_batch(artist, song):
    line = f"{artist} - {song}"

    if line in seen_tracks:
        log(f"[Pandora Thumber] Already in batch: {line}")
        return False

    with BATCH_FILE.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line + "\n")

    seen_tracks.add(line)
    log(f"[Pandora Thumber] Added to batch: {line}")
    return True


def check_full_batch_trigger():
    global batch_full_triggered

    if batch_full_triggered or len(seen_tracks) < BATCH_THRESHOLD:
        return False

    # This is the one transition that causes both the notification and browser pause.
    batch_full_triggered = True
    send_ntfy_notification()
    return True


class TrackHandler(BaseHTTPRequestHandler):
    def send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/track":
            self.send_response(404)
            self.end_headers()
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            track = json.loads(raw_body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            log(f"[Pandora Thumber] Invalid request: {exc}")
            self.send_response(400)
            self.end_headers()
            return

        artist = track.get("artist")
        song = track.get("song")

        if not artist or not song:
            log("[Pandora Thumber] Invalid track: artist and song are required")
            self.send_response(400)
            self.end_headers()
            return

        # Re-read the file on every received track so manual deletion/editing is
        # immediately respected without restarting the receiver.
        refresh_batch_state()

        log(
            "[Pandora Thumber] Received: "
            f"{artist} - {song} "
            f"[{track.get('station', '?')}] rating={track.get('rating', 'none')}"
        )
        append_to_batch(artist, song)

        # pause=True is returned exactly once when this batch first becomes full.
        # Additional songs continue to be logged but will not re-pause Pandora.
        pause = check_full_batch_trigger()
        self.send_json(200, {"pause": pause, "batch_count": len(seen_tracks)})

    def log_message(self, format, *args):
        # Suppress BaseHTTPRequestHandler's default access-log noise.
        return


if __name__ == "__main__":
    server = HTTPServer((HOST, PORT), TrackHandler)
    log(f"[Pandora Thumber] Receiver listening on http://{HOST}:{PORT}")
    log(f"[Pandora Thumber] Batch file: {BATCH_FILE}")
    log(f"[Pandora Thumber] Existing batch tracks: {len(seen_tracks)}")
    log(
        f"[Pandora Thumber] Batch threshold: {BATCH_THRESHOLD} tracks; "
        f"ntfy topic: {NTFY_TOPIC}"
    )
    if batch_full_triggered:
        log("[Pandora Thumber] Existing batch is already full; trigger is disarmed until batch is cleared.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("\n[Pandora Thumber] Receiver stopped.")
    finally:
        server.server_close()
