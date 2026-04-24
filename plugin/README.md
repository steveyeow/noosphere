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

- **Noosphere running** somewhere the plugin can reach. For v0.1 the supported setup is **self-hosted Noosphere on the same machine as Obsidian** — both access the vault folder directly from disk. Cloud Noosphere (where server and Obsidian are on different machines) needs a file-upload variant that's on the roadmap.
- **Obsidian desktop** — vault filesystem access is required. Mobile is not supported (`isDesktopOnly: true`).
- **A corpus** — create one via the Noosphere web UI before configuring the plugin.

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

The plugin makes one HTTP call per sync:

```
POST {serverUrl}/api/v1/corpora/{corpusId}/sync-local
Content-Type: application/json
Authorization: Bearer {apiToken}   # optional for self-hosted

{
  "path": "/Users/you/Obsidian/my-vault",
  "format": "obsidian",
  "prune": false,
  "writeback": true
}
```

The server runs `sync_directory(..., format="obsidian")` against that path, then (if writeback enabled) computes the writeback payload and writes `__noosphere/` files. The same vault is accessible from both the server process and the plugin process — this is why v0.1 requires a co-located setup.

Response shape:

```json
{
  "sync": { "new": 3, "updated": 2, "unchanged": 41, "pruned": 0 },
  "index": { "chunk_count": 312 },
  "writeback": { "written": 1, "skipped_conflict": 0 }
}
```

## Troubleshooting

- **"Corpus lookup failed (404)"** — the corpus ID/slug in settings doesn't exist on the server. Check the Noosphere web UI's Corpora page.
- **"Corpus lookup failed (401)"** — server requires auth. Paste your API token in settings.
- **"Path is not a readable directory on the server"** — the server is running on a different machine from Obsidian, or the vault path contains a symlink the server can't follow. For remote servers, use the CLI (`noosphere sync`) from a shell on the server's machine, not this plugin.
- **Syncs succeed but writeback doesn't appear** — check the server logs. Writeback writes to `<vault>/__noosphere/` using the server process's filesystem permissions. If Obsidian and the server run as different users, the server may not have write access.

## License

MIT.
