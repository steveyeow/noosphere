# Noosphere — Obsidian plugin

Sync your Obsidian vault with a [Noosphere](https://github.com/steveyeow/noosphere) knowledge base. Agents can query your notes through the Noosphere network, and Noosphere-synthesized entity and concept pages land back in your vault as markdown under `__noosphere/`.

This plugin is a thin UX layer on top of the `noosphere sync --obsidian` CLI. Same vault, same behavior, just one click inside Obsidian plus an optional auto-sync-on-save mode.

## What it does

- **Sync now** — ribbon icon and command palette entry. Scans your vault, pushes new/changed notes to Noosphere, fetches synthesized entity + concept pages back.
- **Watch mode** — auto-sync a few seconds after every save (debounced so a burst of saves triggers one sync, not N).
- **Writeback** — Noosphere's compiled entity/concept pages appear in `<vault>/__noosphere/entities/*.md` and `__noosphere/concepts/*.md`. Open them in Obsidian like any other note. Local edits win: if you edit a writeback file, the plugin won't overwrite your changes.
- **Status bar** — shows last sync summary: `3 new · 2 upd · 41 same · wb 1↓`
- **Skipped** — `.obsidian/`, `.trash/`, dotfiles, and `__noosphere/` (the writeback mirror — ingesting it would feedback-loop).

## Requirements

- **Noosphere running** somewhere the plugin can reach — either self-hosted locally (`http://localhost:8420`) or cloud (`https://app.noosphere.wiki`). The plugin reads vault files via Obsidian's API and uploads them over HTTP, so co-location is not required.
- **Obsidian desktop** — the plugin is `isDesktopOnly: true` because vault reads use APIs that require a real filesystem under the hood.
- **A corpus** — use the "Create new" button in plugin settings (creates one on the fly), or pre-create one in the Noosphere web UI and paste its ID.

## Install

### Manual (works today)

1. Download the latest release ZIP from the main Noosphere repo's Releases page (contains `manifest.json`, `main.js`, `styles.css`).
2. Extract it into `<your-vault>/.obsidian/plugins/noosphere-sync/`.
3. In Obsidian: Settings → Community plugins → enable Noosphere.
4. Open Noosphere's settings tab and fill in:
   - **Server URL** — default `http://localhost:8420` for local self-hosted
   - **Corpus ID or slug** — the destination KB
   - **API token** — leave blank for self-hosted, fill for cloud
5. Click "Test" to verify connection, then click the sync ribbon icon.

### From source (for development)

```bash
cd plugin
npm install
npm run build         # produces main.js
```

Then copy `manifest.json`, `main.js`, and `styles.css` into `<your-vault>/.obsidian/plugins/noosphere-sync/`.

For live-reload development: `npm run dev` (rebuilds on save). Use Obsidian's "Reload app without saving" command after edits, or add the [Hot-Reload](https://github.com/pjeby/hot-reload) plugin to skip the reload step.

### Community plugin directory

Planned. When submitted and approved, this plugin will appear in Obsidian's built-in "Browse community plugins" picker. Until then, use manual install above.

## How it talks to Noosphere

Each sync is a small HTTP conversation — entirely content-based, no path sharing needed:

```
GET  /api/v1/corpora/{id}/sync/state       → server's current path→hash map
POST /api/v1/corpora/{id}/sync/upsert      → one call per changed file
DELETE /api/v1/corpora/{id}/sync/doc?path= → one call per deleted file (prune mode)
GET  /api/v1/corpora/{id}/writeback?since= → synthesized entity/concept pages
```

The plugin hashes every local file (SHA-256) and compares against the server's state, only uploading what differs. Writeback is pulled and written into `<vault>/__noosphere/` using Obsidian's adapter API; a per-file hash map in plugin data detects and preserves local edits.

## Troubleshooting

- **"Corpus lookup failed (404)"** — the corpus ID/slug in settings doesn't exist on the server. Click "Create new" in settings to make one, or check the Noosphere web UI's Corpora page.
- **"Corpus lookup failed (401)"** — server requires auth. Paste your API token in settings.
- **Writeback files not appearing** — check the "Writeback" toggle is on. The plugin writes to `<vault>/__noosphere/` via Obsidian's adapter, so there's no permission issue with server processes.
- **Watch mode feels too chatty** — every vault write triggers a debounced sync 1.5s later. For big refactors, toggle watch off via the command palette (`Toggle Noosphere watch mode`), do your work, then toggle back on.

## License

MIT.
