// ==UserScript==
// @name         Pandora Thumber - Track Change POC
// @namespace    https://github.com/jdmack/pandora-thumber
// @version      0.3.0
// @description  Detect Pandora track changes, send metadata to a local receiver, and pause when the batch is ready.
// @match        https://www.pandora.com/*
// @grant        GM_xmlhttpRequest
// @connect      127.0.0.1
// ==/UserScript==

(function () {
    'use strict';

    const POLL_MS = 1000;
    const RECEIVER_URL = 'http://127.0.0.1:8765/track';
    let lastTrackKey = null;

    function text(selector) {
        const el = document.querySelector(selector);
        return el ? el.textContent.trim() : null;
    }

    function getTrackTitle() {
        // Pandora duplicates marquee text for scrolling animation, so prefer the
        // hidden sizing element because it contains the title exactly once.
        return (
            text('[data-qa="playing_track_title"] .Marquee__hiddenSizer') ||
            text('[data-qa="playing_track_title"]')
        );
    }

    function getThumbState() {
        const up = document.querySelector('[data-qa="thumbs_up_button"]');
        const down = document.querySelector('[data-qa="thumbs_down_button"]');

        if (up?.getAttribute('aria-checked') === 'true') return 'up';
        if (down?.getAttribute('aria-checked') === 'true') return 'down';
        return 'none';
    }

    function readCurrentTrack() {
        const song = getTrackTitle();
        const artist = text('[data-qa="playing_artist_name"]');

        if (!song || !artist) return null;

        return {
            station: text('.NowPlayingTopInfoSessionName__link'),
            artist,
            song,
            rating: getThumbState(),
        };
    }

    function pausePandora() {
        // Pandora only exposes pause_button while audio is actively playing.
        // If it is already paused, this selector does not exist, so this is safe.
        const pauseButton = document.querySelector('[data-qa="pause_button"]');

        if (!pauseButton) {
            console.log('[Pandora Thumber] Pandora is already paused or pause button is unavailable.');
            return;
        }

        pauseButton.click();
        console.log('[Pandora Thumber] Batch ready; paused Pandora.');
    }

    function sendTrack(track) {
        GM_xmlhttpRequest({
            method: 'POST',
            url: RECEIVER_URL,
            headers: {
                'Content-Type': 'application/json',
            },
            data: JSON.stringify(track),
            onload(response) {
                console.log(`[Pandora Thumber] Receiver responded ${response.status}`);

                if (response.status !== 200) return;

                try {
                    const result = JSON.parse(response.responseText);
                    console.log(`[Pandora Thumber] Batch count: ${result.batch_count}`);

                    if (result.pause) {
                        pausePandora();
                    }
                } catch (error) {
                    console.warn('[Pandora Thumber] Invalid receiver response', error);
                }
            },
            onerror(error) {
                console.warn('[Pandora Thumber] Could not reach local receiver', error);
            },
        });
    }

    function poll() {
        const track = readCurrentTrack();
        if (!track) return;

        // Artist + song is sufficient for this POC. We can switch to Pandora's
        // track ID later if testing shows a reason to do so.
        const trackKey = `${track.artist}\u0000${track.song}`;

        if (trackKey === lastTrackKey) return;
        lastTrackKey = trackKey;

        console.log('[Pandora Thumber] New track', track);
        sendTrack(track);
    }

    console.log(`[Pandora Thumber] POC loaded; polling every ${POLL_MS} ms.`);
    poll();
    setInterval(poll, POLL_MS);
})();
