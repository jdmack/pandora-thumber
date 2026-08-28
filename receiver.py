from http.server import BaseHTTPRequestHandler, HTTPServer
import json

HOST = "127.0.0.1"
PORT = 8765


def log(message=""):
    print(message, flush=True)


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

        log(
            "[Pandora Thumber] Received: "
            f"{track.get('artist', '?')} - {track.get('song', '?')} "
            f"[{track.get('station', '?')}] rating={track.get('rating', 'none')}"
        )

        self.send_response(204)
        self.end_headers()

    def log_message(self, format, *args):
        # Suppress BaseHTTPRequestHandler's default access-log noise.
        return


if __name__ == "__main__":
    server = HTTPServer((HOST, PORT), TrackHandler)
    log(f"[Pandora Thumber] Receiver listening on http://{HOST}:{PORT}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("\n[Pandora Thumber] Receiver stopped.")
    finally:
        server.server_close()
