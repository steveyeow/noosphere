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

### For users — download a pre-built release (recommended)

1. Open the [Noosphere Releases page](https://github.com/steveyeow/noosphere/releases).
2. On the latest `plugin-vX.Y.Z` release, download the three files: **`manifest.json`**, **`main.js`**, **`styles.css`**.
3. Put them in `<your-vault>/.obsidian/plugins/noosphere-sync/` (create the folder if it doesn't exist).
4. In Obsidian → **Settings → Community plugins**. If this is your first community plugin, click **Turn on community plugins** first (Obsidian's default safety gate).
5. In the Installed plugins list, enable the toggle next to **Noosphere**.
6. A **Noosphere** tab now appears in the left sidebar of Settings. Open it and fill in:
   - **Server URL** — `http://localhost:8420` for local self-hosted, `https://app.noosphere.wiki` for cloud
   - **Corpus ID or slug** — click **Create new** to generate one named after your vault, or paste an existing ID
   - **API token** — leave blank for self-hosted; required for cloud (generate in the Noosphere web UI)
7. Click **Test** to verify the connection, then click the **Sync** ribbon icon (top-left of Obsidian).

That's it. No Node.js required on your side — the plugin artifacts are pre-built by the repo's GitHub Actions workflow on every plugin tag.

### For developers — build from source

```bash
cd plugin
npm install
npm run build         # produces main.js
```

Then copy `manifest.json`, `main.js`, `styles.css` into `<your-vault>/.obsidian/plugins/noosphere-sync/`.

For live-reload development: `npm run dev` (rebuilds on save). Use Obsidian's "Reload app without saving" command after edits, or add the [Hot-Reload](https://github.com/pjeby/hot-reload) plugin to skip the reload step.

### Community plugin directory (future)

Once the plugin is stable, the maintainer will submit it to [obsidianmd/obsidian-releases](https://github.com/obsidianmd/obsidian-releases) for review. After approval, users can install directly from Obsidian's built-in "Browse community plugins" picker. Until then, the Releases-page flow above is the supported path.

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
