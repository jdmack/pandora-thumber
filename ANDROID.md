# Android Client Plan

Pandora Thumber currently has a working browser client (`pandora-thumber.user.js`) that reads Pandora's web-player DOM and sends new tracks to the shared receiver on the LAN.

The intended next client is Android. The goal is the same: when the Pandora Android app starts playing a new song, detect it and POST the track to the existing `receiver.py` service.

Pandora's browser client and Android client have separate recent-song histories, so the receiver now treats them as separate **sources** with independent batches:

- `web` -> `current_batch_web.txt`
- `android` -> `current_batch_android.txt`

Each source has its own duplicate set, count, threshold state, notification, and one-shot pause behavior. Filling or clearing one batch does not affect the other.

## Why this should be possible

Android media apps normally expose playback information through Android's media-session system so the operating system can provide lock-screen controls, notification media controls, Bluetooth/headset controls, Android Auto integration, etc.

Instead of scraping Pandora's Android UI, the Android client should first attempt to consume Pandora's active `MediaSession` through `MediaSessionManager` / `MediaController`.

A normal third-party application cannot simply inspect every application's active media sessions. The practical supported route is to have the user grant the Pandora Thumber app **Notification Listener access**. An enabled notification listener can obtain active media sessions through `MediaSessionManager` and then attach a controller/callback to Pandora's session.

This makes the Android client conceptually cleaner than the browser client: the browser version polls rendered DOM elements because Pandora exposes no interface to our userscript, while Android provides an intentional media-control/session mechanism designed for communication between a media app, the OS, and authorized controllers.

Exact Pandora behavior still needs to be verified experimentally. In particular, confirm which metadata Pandora exposes through its MediaSession on the target Android version/device rather than assuming every desired field is available.

## Proposed architecture

```text
Pandora Android app
      |
      | publishes MediaSession metadata/playback state
      v
Android media-session system
      |
      | Pandora Thumber has Notification Listener access
      v
Pandora Thumber Android app
      |
      | observe Pandora MediaSession metadata changes
      | title / artist / playback state
      v
POST http://<receiver>:8765/track
      | source = "android"
      v
existing receiver.py
      |
      +--> current_batch_android.txt
      +--> Android-specific threshold state
      +--> ntfy when Android batch fills
      +--> {source, batch_count, pause}
                         |
                         v
             Android client pauses Pandora
             through MediaController if supported
```

The receiver protocol is shared between clients, but `source` tells the receiver which Pandora recent-history list the song belongs to.

## Primary approach: MediaSession

The first implementation should use Android's media-session APIs rather than reading notification text.

The proof of concept should:

1. Create a minimal Android app.
2. Declare/provide a `NotificationListenerService` so the user can grant Notification Access.
3. Obtain `MediaSessionManager`.
4. Request the active media sessions available to the notification listener.
5. Identify the session belonging to Pandora by package name.
6. Create/use a `MediaController` for that session.
7. Print the current `MediaMetadata` and playback state for inspection.
8. Register a `MediaController.Callback` and log metadata changes as Pandora advances tracks.

Do **not** start by implementing networking, storage, a UI, or receiver integration. First prove that Pandora exposes usable artist/title metadata and that callbacks reliably occur on song changes.

Unlike the Tampermonkey client, this should normally be event-driven. There should be no reason to poll once per second if Pandora's MediaSession produces reliable metadata-change callbacks.

## Track identity / duplicate protection

The browser client currently uses `artist + song` as its simple in-memory identity and sends only when that key changes. The Android client can initially do the same unless Pandora exposes a stable media ID that provides a compelling reason to use it.

The receiver also protects each source's current batch from duplicate `Artist - Song` lines, so an accidental duplicate Android event should not duplicate the Android batch entry.

## Receiver integration

Once the MediaSession proof of concept works, POST to:

```text
http://<receiver-address>:8765/track
```

The Android payload should explicitly identify itself as `android`:

```json
{
  "source": "android",
  "station": "Carry on Wayward Son Radio",
  "artist": "AC/DC",
  "song": "Get It Hot",
  "rating": "none"
}
```

Artist and song are required. Source should always be `android` for this client. Station name and Pandora thumb state may not be exposed through MediaSession; if unavailable, do not invent them.

The receiver defaults a missing source to `web` for backward compatibility with older Tampermonkey clients, but the Android client should never rely on that default.

The Android app must have normal network/Internet permission and must be able to reach the receiver machine on the local network. The existing receiver listens on TCP 8765 on the LAN.

## Batch-full pause

When the Android batch first reaches the configured threshold, the receiver responds to that Android request with something like:

```json
{
  "source": "android",
  "batch_count": 28,
  "pause": true
}
```

The web batch may be at any count and is unaffected.

For Android, investigate whether the `MediaController` attached to Pandora's session permits calling its transport controls to pause playback. This is the preferred mechanism because media sessions are specifically intended to support external playback controllers.

If it works, the Android behavior becomes:

```text
Pandora changes song
    -> Android client receives metadata callback
    -> POST source=android track to Rapier
    -> receiver appends to current_batch_android.txt
    -> Android batch reaches threshold
    -> receiver sends Android ntfy + pause=true
    -> Android client calls Pandora MediaController pause
```

`pause=true` is returned exactly once for that full Android batch. If the user manually resumes Pandora without clearing `current_batch_android.txt`, subsequent Android songs continue to be captured without repeatedly pausing playback.

Clearing `current_batch_android.txt` below the threshold rearms only the Android trigger. It does not touch the web batch.

## Fallback: notification contents

If Pandora's MediaSession cannot be accessed or does not expose usable metadata, the fallback is the `NotificationListenerService` itself.

A notification listener receives callbacks when applications post/update/remove notifications. Pandora's media notification necessarily contains or references enough information for Android to display its media notification, so inspect the Pandora notification extras as a Plan B and determine whether artist/title can be extracted reliably.

This is less desirable than consuming MediaSession metadata because notification presentation is more application-specific and potentially more fragile. Do not implement notification scraping unless MediaSession testing demonstrates a reason to do so.

## What the Android app does NOT need

Keep the Android client consistent with the philosophy of the existing project. It does not need its own database, listening history, batch-management UI, ChatGPT integration, automatic thumbing, or cloud service.

Its job is narrowly:

```text
Detect Pandora song -> send source=android song to receiver -> honor one-shot pause response
```

The receiver remains the source of truth for the source-specific batch files, threshold state, and ntfy notifications.

## First milestone

Before designing the real app, build the smallest possible diagnostic APK that can answer these questions on the actual phone:

- Can it see Pandora's active MediaSession after Notification Access is granted?
- What package/session identifiers does Pandora expose?
- Does `MediaMetadata` contain correct song title and artist?
- Does metadata change reliably when Pandora advances automatically and when a track is skipped?
- Does the callback work while the diagnostic app is not in the foreground?
- Can its `MediaController` pause Pandora?

If those answers are satisfactory, the rest is mostly wiring the already-proven receiver protocol onto the Android client.