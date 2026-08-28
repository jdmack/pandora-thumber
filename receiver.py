from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path

HOST = "127.0.0.1"
PORT = 8765
BATCH_FILE = Path(__file__).with_name("current_batch.txt")


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


class TrackHandler(BaseHTTPRequestHandler):
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

        log(
            "[Pandora Thumber] Received: "
            f"{artist} - {song} "
            f"[{track.get('station', '?')}] rating={track.get('rating', 'none')}"
        )
        append_to_batch(artist, song)

        self.send_response(204)
        self.end_headers()

    def log_message(self, format, *args):
        # Suppress BaseHTTPRequestHandler's default access-log noise.
        return


if __name__ == "__main__":
    server = HTTPServer((HOST, PORT), TrackHandler)
    log(f"[Pandora Thumber] Receiver listening on http://{HOST}:{PORT}")
    log(f"[Pandora Thumber] Batch file: {BATCH_FILE}")
    log(f"[Pandora Thumber] Existing batch tracks: {len(seen_tracks)}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("\n[Pandora Thumber] Receiver stopped.")
    finally:
        server.server_close()
