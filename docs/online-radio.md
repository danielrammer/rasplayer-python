# Online radio station map

## Control model

**Verified from source:** Online radio has three pages of five stations. Prev
and Next change only `currentPage`, wrap modulo three, and do not open media.
The five generic action buttons select the corresponding station on the
current page. Generic-button release edges remain ignored. Page deltas and
station selections retain the serialized command path's existing sum/latest
coalescing and bounded feedback behavior.

## Station map

| Page | Button | Station | VLC URL |
| ---: | ---: | --- | --- |
| 1 | 1 | SomaFM Metal Detector | `http://ice2.somafm.com/metal-128-mp3` |
| 1 | 2 | SomaFM Underground 80s | `http://ice2.somafm.com/u80s-128-mp3` |
| 1 | 3 | SomaFM The Trip | `http://ice2.somafm.com/thetrip-128-mp3` |
| 1 | 4 | Radio Swiss Classic | `http://stream.srg-ssr.ch/srgssr/rsc_de/mp3/128` |
| 1 | 5 | SomaFM Sonic Universe | `http://ice2.somafm.com/sonicuniverse-128-mp3` |
| 2 | 1 | BluesMusicFan Radio | `http://orbit.citrus3.com:8052/stream` |
| 2 | 2 | Epic Rock Radio | `http://radio.streemlion.com:4200/stream` |
| 2 | 3 | The 1920s Radio Network | `http://65.108.124.70:8181/stream` |
| 2 | 4 | Positively 1990s | `http://streaming.positivity.radio/pr/posi90s/icecast.audio` |
| 2 | 5 | Radio Paradise | `http://stream-uk1.radioparadise.com/mp3-192` |
| 3 | 1 | Rockantenne | `http://mp3channels.webradio.antenne.de/rockantenne` |
| 3 | 2 | 80er-Kulthits | `http://mp3channels.webradio.antenne.de/80er-kulthits` |
| 3 | 3 | Workout Hits | `http://mp3channels.webradio.antenne.de/workout-hits` |
| 3 | 4 | Chillout | `http://mp3channels.webradio.antenne.de/chillout` |
| 3 | 5 | Hitmix | `http://mp3channels.webradio.antenne.de/hitmix` |

Page 3 is the prior five-entry `OnlinePlayer.radios` map, unchanged and in
the same order.

## Endpoint and advertising evidence

**Verified 2026-08-31 and rechecked 2026-09-01:** SomaFM publishes permanent
PLS URLs containing three official non-TLS MP3 relays per channel. The table
uses each playlist's current `File1` direct MP3 relay because the target VLC
command-line playlist layer follows PLS entries but a single libVLC
`MediaPlayer` reports the PLS item as ended instead of opening its subitem.
SomaFM describes its service as independent, listener-supported, and
commercial-free.

**Verified 2026-08-31:** Radio Swiss Classic publishes the MP3 path and states
that its programming is completely advertising-free; it warns that
third-party aggregators may add advertising. BluesMusicFan publishes its
direct Citrus3 mount and describes itself as commercial-free and
listener-supported. Epic Rock Radio states it runs no advertisements; its
official Icecast status publishes the selected HTTP listen URL and identifies
the format as power, progressive, melodic, and symphonic metal.

**Verified 2026-08-31:** The failed Positively 1930s `posi30s` mount returned
HTTP 404 and was rejected. The replacement is The 1920s Radio Network's
official direct 192 kbps MP3 service, whose published schedule is primarily
20s--40s big-band music and whose listen page describes the service as “just
the music.” YouRadio states that its Positivity/decade network is ad-free;
the Positively 1990s direct publisher mount remains live. Radio Paradise
describes itself as ad-free and listener-supported and publishes the selected
European 192 kbps MP3 endpoint.

## Compatibility verification

**Development-machine verified 2026-08-31:** all four SomaFM URLs returned
HTTP 200 PLS content. The six direct streams returned HTTP 200 audio and
sustained MP3 bytes; the rejected Positively 1930s URL returned 404.

**Pi-verified 2026-08-31 before deployment:** all ten new final URLs reached
the Raspberry Pi Buildroot VLC 3.0.21 mpg123 decoder through bounded,
dummy-audio tests. Direct streams began decoding in about 2.6--3.1 seconds;
the four SomaFM playlists decoded continuously through their five-second test
window. The running RasPlayer service remained healthy during these tests.

**Pi-verified during signed deployment on 2026-09-01:** release
`music-radio15-20260901-1` proved the three-page controls and all 15 endpoints
through bounded target VLC 3.0.21 mpg123 checks. Thirteen decoded during the
initial eight-second pass; SomaFM Metal Detector and Underground 80s reached
their official relays but needed a bounded retry, decoding in 10.788 seconds
and within the 15-second verification window respectively. A physical Online
selection then exposed the PLS/libVLC `MediaPlayer` mismatch described above,
so the final table uses direct MP3 relays and a nonblocking 20-second opening
window. RasPlayer remained healthy and `LOCAL_READY` throughout verification.

**Pi-verified final release:** signed release `music-radio15-20260901-2` is
active. The real `OnlinePlayer`/libVLC `MediaPlayer` opened the direct Metal
Detector relay and changed from `State.Opening` to `State.Playing` in
1.034 seconds. Physical Next and Prev each changed one page without reopening
media, emitted one generic acknowledgement, and retained press-only station
selection semantics.

The Buildroot VLC configuration deliberately lacks a TLS client plugin. HTTPS
MRLs therefore fail with `TLS client plugin not available`. The table uses
publisher-operated HTTP endpoints that were actually decoded by the target
instead of retaining HTTPS URLs that work only on the development machine.
`tools/verify_online_streams.py` provides the bounded manual regression check.
