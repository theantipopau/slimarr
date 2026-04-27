# r/usenet Launch Post (Copy/Paste)

## Title

Released: Slimarr (Plex + Usenet) - automatically replace bloated media with smaller releases

## Body

Hey everyone,

I just released **Slimarr**, a tool for people running Plex + Usenet who want to continuously reduce library size without manually curating every file.

Slimarr workflow:

- scan Plex library
- search Usenet via Prowlarr or direct Newznab indexers
- compare candidate releases by size/codec/language/resolution
- send accepted NZBs to the configured downloader
- replace the local media file only when smaller
- refresh Plex and log the savings

Core safety rule: **it never accepts a larger file**.

### Current release info

- Latest installer line: **1.0.0.2** (Windows installer)
- Default downloader: **SABnzbd**
- Also supports **NZBGet** on current main branch builds

### Links

- GitHub: https://github.com/theantipopau/slimarr
- Website/screenshots: https://theantipopau.github.io/slimarr/
- Releases: https://github.com/theantipopau/slimarr/releases

### Feedback I am looking for

- Better scoring rules for choosing releases
- Common Usenet edge cases I should test against
- Any must-have workflow improvements for serious library optimization setups

If this is useful to you, I would love feedback from real-world stacks.
