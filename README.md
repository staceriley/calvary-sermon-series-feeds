# Calvary Bible Feeds

One repository can host every custom Calvary Castle Rock archive feed.

## One-time setup

Create one public repo, for example:

`calvary-bible-feeds`

Upload this package. Then:

1. Run **Actions → Update all Calvary podcast feeds → Run workflow**
2. In **Settings → Pages**, choose:
   - Source: Deploy from a branch
   - Branch: main
   - Folder: `/docs`
3. Subscribe in Podcast Addict with URLs like:
   - `https://staceriley.github.io/calvary-bible-feeds/genesis/feed.xml`
   - `https://staceriley.github.io/calvary-bible-feeds/exodus/feed.xml`

## Adding another book later

You do NOT create another workflow or another Pages site.

Just copy one JSON file under `series/`, rename it, and change:
- slug
- feed title
- archive URL
- artwork URL
- matching keywords
- minimum episode count
- expected titles (optional but recommended)

The one workflow regenerates every feed.

## Important

The `.github` directory is a hidden directory on macOS because its name begins with a dot.
Finder can reveal hidden files with:

Command + Shift + .

The ZIP itself includes `.github/workflows/update-feeds.yml`.
