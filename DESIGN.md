# Pandora Thumber — Original Design Notes

This document preserves the original project README/design notes from before the first working deployment. Some goals and proposed features below were intentionally simplified or abandoned during implementation. See `README.md` for the current behavior and deployment instructions.

# Pandora Thumber

## Goal
I want to create a Pandora station that strictly holds to the musical identity I've chosen for that station. Having ChatGPT tell me if the song fits is much better than me guessing and poisoning the algorithm. 

Needing to stop every song and ask how to thumb it is distracting and not really realistic since I'll just forget. Pandora only exposes a limited rolling session history of 30 songs that you can go back and thumb. It is also very annoying because it shows a panning sequence of album art... not the song name and you have to click to scroll then thumb, click to scroll, etc. And to even collect the list is tedious because I have to click through each song and copy paste the title and artist which are on different lines. So generating a list of the last 30 songs manually to provide to ChatGPT in a batch is extremely tedious and I'm trying to work on the station while working on other stuff.

So the actual goal is to make an application that records the songs playing on the Pandora station as they come up and writes them to a temporary text file. Then when it has hit 29 songs since the last reset, the application sends me an alert via the ntfy app, I copy paste that list of songs, put them in ChatGPT and get the thumb recommendations, then, unfortunately manually, I click through the songs and thumb them. Not ideal but many times better than not having a recording app. Then the app is reset and collects the next batch of songs. 

Secondary goal is to keep a list of the Thumbs Up songs so that I can eventually make local playlists and not be so dependent on Pandora.

## Desired behavior

While Pandora is playing:

- Detect when the currently playing track changes.
- Read the **song title and artist directly from Pandora's DOM**.
- If available, also capture:
    - Station name
    - Thumb Up / Thumb Down status
- Send each new track to a small local Python service.
- Store the history persistently on disk.
    - Write to Song Batch file containing the current 29 song batch
    - Write Thumbed Up songs to the <station> Playlist file.
- Do not create duplicate entries just because Pandora's DOM updates multiple times during the same song.

For storage, let's discuss whether **CSV or SQLite** makes more sense before implementing it. I want the data to remain easy to inspect/export regardless.

A record should contain at minimum:

`timestamp | station | artist | song`

I'd also like to eventually support:

`timestamp | station | artist | song | rating`

## Rating support

Eventually I'd like the logger to detect when I click Pandora's existing Thumb Up or Thumb Down controls and update the corresponding history entry.

We can also consider keyboard shortcuts later, but don't make that part of the initial implementation.

## Longer-term possibilities

Once basic logging works, we may expand it to:

- Analyze which artists/songs I listen to most.
- Compare different Pandora stations.
- Track thumbs by station.
- Detect station convergence over time.
- Export subsets to CSV.
- Build a personal database of artists and songs I've encountered.
- Potentially enrich tracks later with genre/year/album metadata from another source.

## Development approach

Let's build this incrementally rather than designing the entire finished application upfront.

First, investigate the **current Pandora web player's DOM** and determine the most reliable way for Tampermonkey to obtain:

1. Current song title
2. Current artist
3. Current station
4. Playback/track-change events
5. Thumb state, if readily accessible

I can provide screenshots, browser DevTools output, copied HTML, selectors, etc. as needed.

Once we understand Pandora's current DOM, let's make the smallest possible Tampermonkey proof-of-concept that detects track changes and prints the extracted metadata to the browser console.

After that works reliably, we'll add the Python service and persistent storage.

Please favor **simple, observable, debuggable solutions** over clever abstractions. I want to understand what each piece is doing and be able to troubleshoot it when Pandora inevitably changes its web UI.
