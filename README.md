# Pandora Thumber

Pandora Thumber is a small LAN utility that records songs as they play in the Pandora web player and builds a copy/paste-friendly batch for later review.

It exists primarily to make it practical to use ChatGPT to review a Pandora station in batches: let Pandora play in the background, collect the songs automatically, then review and thumb them before they fall out of Pandora's limited session history.

The implementation is deliberately simple: a Tampermonkey userscript watches Pandora in the browser and sends new tracks over HTTP to a tiny Python receiver. The receiver appends them to `current_batch.txt`. When the batch reaches the configured threshold, it sends an ntfy notification and tells the browser to pause Pandora once.

## Architecture

```text
Pandora web player
      |
      | Tampermonkey reads the DOM
      v
pandora-thumber.user.js
      |
      | HTTP POST /track
      | {station, artist, song, rating}
      v
receiver.py on the LAN server
      |
      +--> current_batch.txt
      +--> ntfy.sh notification when batch becomes full
      |
      +--> HTTP response {batch_count, pause}
                         |
                         v
              userscript clicks Pandora Pause
```

The receiver is intended to run on an always-available machine on the local network (currently Rapier). Any computer on the LAN with the userscript installed can report its Pandora tracks to that receiver.

## Files

- `pandora-thumber.user.js` — Tampermonkey userscript that watches Pandora and talks to the receiver.
- `receiver.py` — Python HTTP receiver, batch writer, threshold state, and ntfy notification logic.
- `current_batch.txt` — runtime file created beside `receiver.py`. One `Artist - Song` entry per line. This is the file to copy into ChatGPT and then manually clear/delete.
- `DESIGN.md` — original project goals and design notes preserved from development. Some ideas there were intentionally not implemented.

## How track detection works

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

The userscript keeps polling even after the batch is full. A full batch does **not** disable logging.

## Batch behavior and manual workflow

The current batch threshold is configured in `receiver.py`:

```python
BATCH_THRESHOLD = 28
```

The intended workflow is:

1. Start the receiver and use Pandora normally.
2. Each new unique song is appended to `current_batch.txt` as `Artist - Song`.
3. When the batch first reaches `BATCH_THRESHOLD`, the receiver sends an ntfy notification on topic `wolfswatch-pandora-thumber`.
4. That same HTTP response tells the userscript to click Pandora's Pause button.
5. Copy the contents of `current_batch.txt` into the ChatGPT station-review conversation.
6. Manually work through Pandora's recent-song history and apply the recommended thumbs.
7. Delete `current_batch.txt` or clear its contents.
8. Press Play in Pandora and continue normally.

There is deliberately no automatic batch clearing, automatic resume, or repeated enforcement of Pause. **The human is the workflow controller.**

If the batch becomes full and you decide you cannot deal with it yet, just press Play. The userscript continues detecting tracks and the receiver continues appending them to the existing batch. It will not pause Pandora again for that same full batch.

The receiver re-reads `current_batch.txt` whenever it receives a track. Once the file contains fewer than `BATCH_THRESHOLD` entries, the full-batch trigger is rearmed automatically. Therefore manually deleting or clearing the file is the reset mechanism; the receiver does not need to be restarted.

If the receiver itself is restarted while an existing batch is already at or above the threshold, it assumes that batch has already triggered. It will not send another notification or pause until the batch has first been cleared below the threshold.

## Receiver deployment

### Requirements

The receiver uses only the Python standard library. No `pip install` step is required.

Install a reasonably current Python 3 release, clone this repository onto the server, and run:

```bash
python receiver.py
```

On startup it prints the listening address, batch-file location, existing batch count, threshold, and ntfy topic.

### Listen on the LAN

For a server deployment, `receiver.py` should contain:

```python
HOST = "0.0.0.0"
PORT = 8765
```

`0.0.0.0` means the receiver listens on the machine's network interfaces instead of accepting only connections from itself. Clients do **not** use `0.0.0.0` as the destination; they use the server's actual LAN IP address or a resolvable hostname.

For long-term use, give the receiver machine a stable address — preferably a DHCP reservation in the router, a static LAN IP, or a hostname that resolves reliably on the LAN. Otherwise a DHCP address change will require updating every userscript.

### Windows Firewall

The server must permit inbound TCP connections to port `8765` on the local/private network.

From an elevated PowerShell prompt, a suitable rule can be created with:

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

For example, if Rapier is `192.168.1.61`:

```javascript
// @connect      192.168.1.61
```

and:

```javascript
const RECEIVER_URL = 'http://192.168.1.61:8765/track';
```

`@connect` grants the Tampermonkey script permission to contact that host. `RECEIVER_URL` is the address the script actually POSTs to.

If the server's IP changes, update **both** values and save the userscript.

The repository currently contains the deployed Rapier address. After rebuilding/replacing Rapier, verify that the address is still correct rather than assuming the old value survived.

## Tampermonkey setup on a client

1. Install the Tampermonkey browser extension.
2. Open the Tampermonkey dashboard and create a new userscript.
3. Replace the generated template with the complete contents of `pandora-thumber.user.js` from this repository.
4. Verify the `@connect` and `RECEIVER_URL` values point to the receiver server.
5. Save the userscript and make sure it is enabled.
6. Open or reload Pandora.

The script matches `https://www.pandora.com/*` and runs automatically on Pandora pages.

**Important during development/troubleshooting:** saving or toggling a Tampermonkey script does not necessarily tear down JavaScript that was already injected into an existing Pandora tab. After editing the userscript, reload the Pandora page to guarantee the new version is running.

Pandora currently loads paused by default. Pandora Thumber intentionally does not auto-play it; press Play yourself.

## ntfy setup

The receiver publishes the full-batch alert to:

```text
wolfswatch-pandora-thumber
```

Subscribe to that topic in the ntfy app on any device that should receive the notification.

The notification is sent through `ntfy.sh` directly by `receiver.py`. If the ntfy request fails, the receiver logs the error but continues accepting and recording tracks.

## Troubleshooting

### Is the userscript detecting songs?

Open the browser DevTools console on the Pandora tab. On load you should see a Pandora Thumber startup message. When the song changes, you should see a `New track` object containing station, artist, song, and rating, followed by the receiver's HTTP response and batch count.

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
[Pandora Thumber] Received: AC/DC - Get It Hot [Carry on Wayward Son Radio] rating=none
[Pandora Thumber] Added to batch: AC/DC - Get It Hot
```

### `current_batch.txt` does not exist

The file is created when the receiver first appends a track. It does not need to exist before startup.

### Receiver output appears only after Ctrl+C

Python stdout can be buffered in some terminal environments. The receiver's logging uses `flush=True` specifically to avoid this problem. If this behavior returns after modifying the logger, check that output is still being explicitly flushed.

### Pandora changed its UI

If track detection suddenly stops while the userscript is otherwise running, inspect Pandora's current player controls and track information in browser DevTools. The `data-qa` selectors listed in **How track detection works** are the first things to verify. Pandora changing those DOM attributes is the most likely future maintenance point.

## Intentional non-features

Pandora Thumber is not intended to be a comprehensive listening-history or analytics system. The final implementation intentionally stayed smaller than some of the original design ideas.

It currently does not automatically clear batches, automatically resume Pandora, repeatedly pause a full batch, maintain a database, provide a UI, or automate applying Pandora thumbs. Station and current thumb state are sent to the receiver for observability, but the persistent batch itself remains the deliberately simple `Artist - Song` text file.

See `DESIGN.md` for the original development goals and ideas that were considered.