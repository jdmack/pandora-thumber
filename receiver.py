from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
from urllib import request, error

HOST = "0.0.0.0"
PORT = 8765
BATCH_THRESHOLD = 28
NTFY_TOPIC = "wolfswatch-pandora-thumber"
NTFY_URL = f"https://ntfy.sh/{NTFY_TOPIC}"

BASE_DIR = Path(__file__).parent
LEGACY_BATCH_FILE = BASE_DIR / "current_batch.txt"
BATCH_FILES = {
    "web": BASE_DIR / "current_batch_web.txt",
    "android": BASE_DIR / "current_batch_android.txt",
}


def log(message=""):
    print(message, flush=True)


def migrate_legacy_web_batch():
    """Move the old single batch file to the new web-specific filename once."""
    web_file = BATCH_FILES["web"]

    if LEGACY_BATCH_FILE.exists() and not web_file.exists():
        LEGACY_BATCH_FILE.replace(web_file)
        log(
            "[Pandora Thumber] Migrated legacy current_batch.txt "
            "to current_batch_web.txt."
        )


def load_existing_tracks(batch_file):
    if not batch_file.exists():
        return set()

    return {
        line.strip()
        for line in batch_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


migrate_legacy_web_batch()

# Each Pandora client has its own recent-history list, so each source must have
# independent duplicate tracking and full-batch trigger state.
batches = {}
for source, batch_file in BATCH_FILES.items():
    seen_tracks = load_existing_tracks(batch_file)
    batches[source] = {
        "file": batch_file,
        "seen_tracks": seen_tracks,
        # If we start while an old batch is already full, assume it already fired.
        # Deleting/clearing that source's file below threshold rearms only it.
        "full_triggered": len(seen_tracks) >= BATCH_THRESHOLD,
    }


def refresh_batch_state(source):
    batch = batches[source]
    batch["seen_tracks"] = load_existing_tracks(batch["file"])

    if len(batch["seen_tracks"]) < BATCH_THRESHOLD and batch["full_triggered"]:
        batch["full_triggered"] = False
        log(
            f"[Pandora Thumber] {source.upper()} batch is below threshold; "
            "full-batch trigger rearmed."
        )


def send_ntfy_notification(source):
    batch = batches[source]
    count = len(batch["seen_tracks"])
    filename = batch["file"].name
    source_label = source.upper()
    body = f"Pandora {source_label} batch is ready: {count} songs in {filename}"

    req = request.Request(
        NTFY_URL,
        data=body.encode("utf-8"),
        method="POST",
        headers={
            "Title": f"Pandora Thumber - {source_label}",
            "Priority": "default",
            "Tags": "musical_note",
        },
    )

    try:
        with request.urlopen(req, timeout=10) as response:
            response.read()
        log(f"[Pandora Thumber] {source_label} ntfy alert sent: {count} tracks")
    except (error.URLError, TimeoutError, OSError) as exc:
        log(f"[Pandora Thumber] {source_label} ntfy alert failed: {exc}")


def append_to_batch(source, artist, song):
    batch = batches[source]
    line = f"{artist} - {song}"

    if line in batch["seen_tracks"]:
        log(f"[Pandora Thumber] {source.upper()} already in batch: {line}")
        return False

    with batch["file"].open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line + "\n")

    batch["seen_tracks"].add(line)
    log(f"[Pandora Thumber] {source.upper()} added to batch: {line}")
    return True


def check_full_batch_trigger(source):
    batch = batches[source]

    if batch["full_triggered"] or len(batch["seen_tracks"]) < BATCH_THRESHOLD:
        return False

    # This source has just crossed its threshold. Notification and pause apply
    # only to the client whose independent recent-history batch became full.
    batch["full_triggered"] = True
    send_ntfy_notification(source)
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

        # Backward compatibility: existing browser userscripts do not send a
        # source yet, so missing/empty source means web.
        source = str(track.get("source") or "web").lower()

        if not artist or not song:
            log("[Pandora Thumber] Invalid track: artist and song are required")
            self.send_response(400)
            self.end_headers()
            return

        if source not in batches:
            log(f"[Pandora Thumber] Invalid track source: {source}")
            self.send_json(
                400,
                {"error": f"source must be one of: {', '.join(sorted(batches))}"},
            )
            return

        # Re-read only this source's file on every received track so manual
        # deletion/editing immediately rearms that source without affecting the other.
        refresh_batch_state(source)

        log(
            f"[Pandora Thumber] Received ({source.upper()}): "
            f"{artist} - {song} "
            f"[{track.get('station', '?')}] rating={track.get('rating', 'none')}"
        )
        append_to_batch(source, artist, song)

        # pause=True is returned exactly once when this source's batch first
        # becomes full. The other source's state is completely independent.
        pause = check_full_batch_trigger(source)
        self.send_json(
            200,
            {
                "source": source,
                "pause": pause,
                "batch_count": len(batches[source]["seen_tracks"]),
            },
        )

    def log_message(self, format, *args):
        # Suppress BaseHTTPRequestHandler's default access-log noise.
        return


if __name__ == "__main__":
    server = HTTPServer((HOST, PORT), TrackHandler)
    log(f"[Pandora Thumber] Receiver listening on http://{HOST}:{PORT}")
    log(
        f"[Pandora Thumber] Batch threshold: {BATCH_THRESHOLD} tracks; "
        f"ntfy topic: {NTFY_TOPIC}"
    )

    for source, batch in batches.items():
        log(
            f"[Pandora Thumber] {source.upper()} batch: {batch['file']} "
            f"({len(batch['seen_tracks'])} existing tracks)"
        )
        if batch["full_triggered"]:
            log(
                f"[Pandora Thumber] {source.upper()} batch is already full; "
                "trigger is disarmed until that batch is cleared."
            )

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("\n[Pandora Thumber] Receiver stopped.")
    finally:
        server.server_close()
