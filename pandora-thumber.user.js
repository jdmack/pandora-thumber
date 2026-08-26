// ==UserScript==
// @name         Pandora Thumber - Track Change POC
// @namespace    https://github.com/jdmack/pandora-thumber
// @version      0.1.0
// @description  Detect Pandora track changes and print current metadata to the browser console.
// @match        https://www.pandora.com/*
// @grant        none
// ==/UserScript==

(function () {
    'use strict';

    const POLL_MS = 1000;
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

    function poll() {
        const track = readCurrentTrack();
        if (!track) return;

        // Artist + song is sufficient for this POC. We can switch to Pandora's
        // track ID later if testing shows a reason to do so.
        const trackKey = `${track.artist}\u0000${track.song}`;

        if (trackKey === lastTrackKey) return;
        lastTrackKey = trackKey;

        console.log('[Pandora Thumber] New track', track);
    }

    console.log(`[Pandora Thumber] POC loaded; polling every ${POLL_MS} ms.`);
    poll();
    setInterval(poll, POLL_MS);
})();
