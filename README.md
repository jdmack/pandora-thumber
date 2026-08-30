# Pandora Thumber

Pandora Thumber is a small LAN utility that records songs as they play in Pandora clients and builds copy/paste-friendly batches for later review.

It exists primarily to make it practical to use ChatGPT to review a Pandora station in batches: let Pandora play in the background, collect the songs automatically, then review and thumb them before they fall out of Pandora's limited recent-history UI.

The implementation is deliberately simple. A client detects new tracks and sends them over HTTP to a tiny Python receiver. The receiver appends them to a source-specific text file. When that source's batch reaches the configured threshold, it sends an ntfy notification and tells only that client to pause once.

The browser client is implemented as a Tampermonkey userscript. An Android client is planned; see `ANDROID.md`.

## Architecture

```text
Pandora web player                         Pandora Android app
      |                                            |
      | Tampermonkey reads DOM                     | Android MediaSession (planned)
      v                                            v
pandora-thumber.user.js                    Android client (planned)
      |                                            |
      | source = web                               | source = android
      +-------------------- HTTP POST /track ------+
                              |
                              v
                     receiver.py on LAN server
                              |
              +---------------+----------------+
              |                                |
              v                                v
   current_batch_web.txt            current_batch_android.txt
       independent state                independent state
              |                                |
              +------------ ntfy / pause ------+
```

Pandora's browser and Android clients have separate recent-song histories, so Pandora Thumber deliberately treats them as separate sources. A full web batch does not affect the Android batch, and vice versa.

The receiver currently recognizes:

- `web`
- `android`

If a client omits `source`, the receiver defaults it to `web` for backward compatibility with the original Tampermonkey client.

## Files

- `pandora-thumber.user.js` — Tampermonkey browser client.
- `receiver.py` — Python HTTP receiver, source-specific batch writer, threshold state, and ntfy notification logic.
- `current_batch_web.txt` — runtime web-client batch, one `Artist - Song` per line.
- `current_batch_android.txt` — runtime Android-client batch, one `Artist - Song` per line.
- `ANDROID.md` — Android client design and implementation plan.
- `DESIGN.md` — original project goals/design notes from development.

On first startup after upgrading from the original single-batch receiver, if `current_batch.txt` exists and `current_batch_web.txt` does not, the receiver automatically renames the old file to `current_batch_web.txt`.

## Client/receiver protocol

Clients POST JSON to:

```text
http://<receiver-address>:8765/track
```

Conceptually:

```json
{
  "source": "web",
  "station": "Carry on Wayward Son Radio",
  "artist": "AC/DC",
  "song": "Get It Hot",
  "rating": "none"
}
```

`artist` and `song` are required. `source` defaults to `web` if omitted. Unknown sources are rejected.

The response is:

```json
{
  "source": "web",
  "batch_count": 28,
  "pause": true
}
```

`pause` becomes `true` exactly once when that particular source's batch first reaches the threshold.

## How browser track detection works

The userscript does not hook into Pandora's internal JavaScript or API. It simply inspects the rendered Pandora page once per second (`POLL_MS = 1000`).

The important Pandora DOM elements are currently:

- Song: `[data-qa="playing_track_title"]`
- Artist: `[data-qa="playing_artist_name"]`
- Station: `.NowPlayingTopInfoSessionName__link`
- Thumb Up: `[data-qa="thumbs_up_button"]`
- Thumb Down: `[data-qa="thumbs_down_button"]`
- Pause button while playing: `[data-qa="pause_button"]`
- Play button while paused: `[data-qa="play_button"]`

Pandora's song-title marquee contains duplicate visible text for its scrolling animation, so the script prefers the `.Marquee__hiddenSizer` child inside the track-title element, which contains the title once.

Every poll reads the current artist and song and builds an in-memory key from `artist + song`. If it is the same key as the previous poll, nothing happens. When the key changes, the userscript treats it as a new track and POSTs the track metadata to the receiver.

This is intentionally polling rather than a MutationObserver or integration with Pandora internals: it is easy to understand, observe in DevTools, and repair if Pandora changes its UI.

The userscript keeps polling even after the web batch is full. A full batch does **not** disable logging.

## Batch behavior and manual workflow

The batch threshold is configured globally in `receiver.py`:

```python
BATCH_THRESHOLD = 28
```

The threshold value is shared, but each source has completely independent batch state.

For the browser workflow:

1. Start the receiver and use Pandora normally.
2. Each new unique web song is appended to `current_batch_web.txt` as `Artist - Song`.
3. When the web batch first reaches `BATCH_THRESHOLD`, the receiver sends an ntfy notification identifying the WEB source.
4. That same HTTP response tells the browser userscript to click Pandora's Pause button.
5. Copy `current_batch_web.txt` into the ChatGPT station-review conversation.
6. Manually work through the browser Pandora recent-song history and apply the recommended thumbs.
7. Delete `current_batch_web.txt` or clear its contents.
8. Press Play and continue.

The Android workflow will be identical using `current_batch_android.txt` and the Android recent-history list.

There is deliberately no automatic batch clearing, automatic resume, or repeated enforcement of Pause. **The human is the workflow controller.**

If one source becomes full and you resume Pandora without clearing it, new tracks from that source keep being appended but it will not notify or pause again for the same full batch.

The receiver re-reads only the relevant source's batch file whenever it receives a track. Once that file contains fewer than `BATCH_THRESHOLD` entries, that source's full-batch trigger rearms automatically. Clearing the web file has no effect on Android state, and clearing the Android file has no effect on web state.

If the receiver restarts while either source is already at or above threshold, that source is assumed to have already triggered and remains disarmed until its own file is cleared below threshold.

## Receiver deployment

### Requirements

The receiver uses only the Python standard library. No `pip install` step is required.

Install a reasonably current Python 3 release, clone this repository onto the server, and run:

```bash
python receiver.py
```

On startup it prints the listening address, threshold/ntfy settings, and the filename/count/full-state for each source.

### Listen on the LAN

For a server deployment, `receiver.py` should contain:

```python
HOST = "0.0.0.0"
PORT = 8765
```

`0.0.0.0` means the receiver listens on the machine's network interfaces instead of accepting only connections from itself. Clients do **not** use `0.0.0.0` as the destination; they use the server's actual LAN IP address or a resolvable hostname.

For long-term use, give the receiver machine a stable address — preferably a DHCP reservation in the router, a static LAN IP, or a hostname that resolves reliably on the LAN. Otherwise a DHCP address change will require updating clients.

### Windows Firewall

The server must permit inbound TCP connections to port `8765` on the local/private network.

From an elevated PowerShell prompt:

```powershell
New-NetFirewallRule -DisplayName "Pandora Thumber Receiver" -Direction Inbound -Protocol TCP -LocalPort 8765 -Action Allow -Profile Private
```

Keep this limited to the Private network profile. The receiver has no authentication and is designed for a trusted home LAN, not exposure to the public Internet.

To remove the rule later:

```powershell
Remove-NetFirewallRule -DisplayName "Pandora Thumber Receiver"
```

## Configure the receiver target in the userscript

The userscript contains the receiver address in **two places**. Both must point at the server.

For example, if the server is `192.168.1.61`:

```javascript
// @connect      192.168.1.61
```

and:

```javascript
const RECEIVER_URL = 'http://192.168.1.61:8765/track';
```

`@connect` grants Tampermonkey permission to contact that host. `RECEIVER_URL` is the address the script actually POSTs to.

If the server's IP changes, update **both** values and save the userscript.

The current userscript predates explicit source tagging and therefore may omit `source`; the receiver intentionally interprets that as `web`. A future cleanup can make the browser client send `source: "web"` explicitly without changing receiver behavior.

## Tampermonkey setup on a client

1. Install the Tampermonkey browser extension.
2. Open the Tampermonkey dashboard and create a new userscript.
3. Replace the generated template with the complete contents of `pandora-thumber.user.js` from this repository.
4. Verify the `@connect` and `RECEIVER_URL` values point to the receiver server.
5. Save the userscript and make sure it is enabled.
6. Open or reload Pandora.

The script matches `https://www.pandora.com/*` and runs automatically on Pandora pages.

**Important during development/troubleshooting:** saving or toggling a Tampermonkey script does not necessarily tear down JavaScript already injected into an existing Pandora tab. After editing the userscript, reload the Pandora page to guarantee the new version is running.

Pandora currently loads paused by default. Pandora Thumber intentionally does not auto-play it; press Play yourself.

## ntfy setup

The receiver publishes full-batch alerts to:

```text
wolfswatch-pandora-thumber
```

Notifications identify whether the **WEB** or **ANDROID** batch became full.

Subscribe to that topic in the ntfy app on any device that should receive the notification.

The notification is sent through `ntfy.sh` directly by `receiver.py`. If the ntfy request fails, the receiver logs the error but continues accepting and recording tracks.

## Troubleshooting

### Is the browser userscript detecting songs?

Open browser DevTools on the Pandora tab. On load you should see a Pandora Thumber startup message. When the song changes, you should see a `New track` object containing station, artist, song, and rating, followed by the receiver's HTTP response and batch count.

If there is no startup message, verify Tampermonkey is enabled for Pandora and reload the page.

### The userscript detects tracks but the receiver sees nothing

Check, in roughly this order:

1. `receiver.py` is running on the server.
2. The server still has the LAN IP configured in `@connect` and `RECEIVER_URL`.
3. TCP port `8765` is allowed through the server's Windows Firewall on the Private profile.
4. Client and server can reach each other on the LAN.
5. The Pandora tab was reloaded after any userscript edits.

A successful receiver log looks approximately like:

```text
[Pandora Thumber] Received (WEB): AC/DC - Get It Hot [Carry on Wayward Son Radio] rating=none
[Pandora Thumber] WEB added to batch: AC/DC - Get It Hot
```

### A batch file does not exist

Each source file is created when the receiver first appends a track for that source. An Android batch file will not exist until an Android client has actually reported something.

### Receiver output appears only after Ctrl+C

Python stdout can be buffered in some terminal environments. The receiver's logging uses `flush=True` specifically to avoid this problem. If this behavior returns after modifying the logger, check that output is still being explicitly flushed.

### Pandora changed its browser UI

If browser track detection suddenly stops while the userscript is otherwise running, inspect Pandora's current player controls and track information in DevTools. The `data-qa` selectors listed in **How browser track detection works** are the first things to verify.

## Intentional non-features

Pandora Thumber is not intended to be a comprehensive listening-history or analytics system.

It currently does not automatically clear batches, automatically resume Pandora, repeatedly pause a full batch, maintain a database, provide a UI, or automate applying Pandora thumbs. Station and current thumb state are diagnostic metadata; persistent batching remains deliberately simple text files.

See `DESIGN.md` for the original development goals and `ANDROID.md` for the planned Android client.