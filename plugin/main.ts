/**
 * Noosphere plugin — Obsidian entry point.
 *
 * Cloud-capable by design: every sync talks to the Noosphere server over
 * HTTP, reading file contents from the vault (via Obsidian's APIs) and
 * uploading them. The server can be self-hosted local OR noosphere.wiki;
 * the plugin doesn't care.
 *
 * Sync algorithm (runs on demand and under watch mode):
 *   1. Enumerate eligible .md files in the vault (skip .obsidian/, .trash/,
 *      dotfiles, __noosphere/)
 *   2. Hash each file's content (SHA-256 hex) locally
 *   3. GET /sync/state — server returns its current (path → hash) map
 *   4. For each local file whose hash differs OR doesn't exist on server:
 *        POST /sync/upsert { path, content }
 *   5. For each server path missing locally (if prune enabled):
 *        DELETE /sync/doc?path=X
 *   6. GET /writeback?since=<last seen> — server returns synthesized
 *      entity + concept pages as { files: [{path, content}] }
 *   7. Write writeback files into vault's __noosphere/ folder using
 *      Obsidian's adapter API, with hash-based conflict detection so
 *      local edits win
 *   8. Persist state (last writeback timestamp + per-file hashes)
 *
 * Watch mode hooks vault events; sync runs debounced 1.5s after a burst.
 *
 * The plugin stores its cross-sync state in Obsidian's plugin data
 * (this.loadData / this.saveData) — same blob as settings. Two tiny
 * helpers (state.writebackSeenAt, state.writebackHashes) track conflict
 * detection between runs.
 */

import {
  FileSystemAdapter,
  Notice,
  Plugin,
  TFile,
  debounce,
  normalizePath,
} from "obsidian";
import { NoosphereClient, sha256Hex } from "./client";
import { DEFAULT_SETTINGS, NoosphereSettings, NoosphereSettingTab } from "./settings";

type PluginState = NoosphereSettings & {
  // Last `generated_at` the server returned on writeback. Sent as ?since=
  // on the next call so we only pull changed files.
  writebackSeenAt?: string;
  // path → sha256 of last content we wrote to disk for writeback. Used to
  // detect local edits (hash on disk differs from last-written hash).
  writebackHashes?: Record<string, string>;
};

const WRITEBACK_ROOT = "__noosphere";

function isWatched(path: string): boolean {
  if (!path.toLowerCase().endsWith(".md")) return false;
  const parts = path.split("/");
  if (parts.some((p) => p.startsWith("."))) return false;
  if (parts.some((p) => p === WRITEBACK_ROOT)) return false;
  return true;
}

export default class NoospherePlugin extends Plugin {
  settings!: NoosphereSettings;
  state!: PluginState;
  statusBarEl: HTMLElement | null = null;
  private debouncedSync: ((reason: string) => void) | null = null;
  private vaultEventRefs: any[] = [];
  private syncing = false;

  async onload(): Promise<void> {
    await this.loadSettings();

    this.statusBarEl = this.addStatusBarItem();
    this.renderStatus("idle");

    this.addRibbonIcon("sync", "Noosphere — sync now", async () => this.syncNow("ribbon"));

    this.addCommand({
      id: "noosphere-sync-now",
      name: "Sync vault with Noosphere",
      callback: async () => this.syncNow("command"),
    });

    this.addCommand({
      id: "noosphere-toggle-watch",
      name: "Toggle Noosphere watch mode",
      callback: async () => {
        this.settings.watchMode = !this.settings.watchMode;
        await this.saveSettings();
        this.updateWatchMode();
        new Notice(`Noosphere watch mode: ${this.settings.watchMode ? "on" : "off"}`);
      },
    });

    this.addCommand({
      id: "noosphere-open-settings",
      name: "Open Noosphere settings",
      callback: () => {
        (this.app as any).setting.open();
        (this.app as any).setting.openTabById("noosphere-sync");
      },
    });

    this.addSettingTab(new NoosphereSettingTab(this.app, this));

    this.updateWatchMode();
  }

  onunload(): void {
    this.disableWatchMode();
  }

  async loadSettings(): Promise<void> {
    const raw = (await this.loadData()) ?? {};
    this.settings = Object.assign({}, DEFAULT_SETTINGS, raw);
    this.state = Object.assign(
      {
        writebackSeenAt: "",
        writebackHashes: {},
      },
      raw,
      this.settings
    ) as PluginState;
  }

  async saveSettings(): Promise<void> {
    // Persist both user-facing settings and internal state in one blob.
    await this.saveData({
      ...this.settings,
      writebackSeenAt: this.state.writebackSeenAt ?? "",
      writebackHashes: this.state.writebackHashes ?? {},
    });
  }

  updateWatchMode(): void {
    this.disableWatchMode();
    if (!this.settings.watchMode) return;

    this.debouncedSync = debounce(
      (reason: string) => this.syncNow(reason),
      1500,
      true
    );

    this.vaultEventRefs.push(
      this.app.vault.on("modify", (f) => {
        if (f instanceof TFile && isWatched(f.path)) this.debouncedSync?.("modify:" + f.path);
      }),
      this.app.vault.on("create", (f) => {
        if (f instanceof TFile && isWatched(f.path)) this.debouncedSync?.("create:" + f.path);
      }),
      this.app.vault.on("delete", (f) => {
        if (f instanceof TFile && isWatched(f.path)) this.debouncedSync?.("delete:" + f.path);
      }),
      this.app.vault.on("rename", (f, oldPath) => {
        if (f instanceof TFile && (isWatched(f.path) || isWatched(oldPath))) {
          this.debouncedSync?.("rename:" + f.path);
        }
      })
    );
    this.vaultEventRefs.forEach((ref) => this.registerEvent(ref));
  }

  disableWatchMode(): void {
    this.vaultEventRefs.forEach((ref) => this.app.vault.offref(ref));
    this.vaultEventRefs = [];
    this.debouncedSync = null;
  }

  async syncNow(_reason: string): Promise<void> {
    if (this.syncing) return;
    const { serverUrl, corpusId, apiToken, writeback, prune } = this.settings;
    if (!serverUrl || !corpusId) {
      new Notice("Noosphere: set server URL and corpus in settings first");
      return;
    }
    this.syncing = true;
    this.renderStatus("syncing");

    const client = new NoosphereClient(serverUrl, apiToken);

    try {
      const stats = await this.runSyncPhases(client, {
        corpusId,
        prune,
        writeback,
      });
      const wbPart = stats.writeback
        ? ` · wb ${stats.writeback.written}↓${
            stats.writeback.skippedConflict ? ` ${stats.writeback.skippedConflict}⊘` : ""
          }`
        : "";
      const msg = `${stats.created} new · ${stats.updated} upd · ${stats.unchanged} same${
        stats.pruned ? " · " + stats.pruned + " pruned" : ""
      }${wbPart}`;
      this.settings.lastSyncAt = new Date().toISOString();
      await this.saveSettings();
      this.renderStatus("ok", msg);
      if (stats.created || stats.updated || stats.pruned || (stats.writeback && stats.writeback.written)) {
        new Notice(`Noosphere: ${msg}`);
      }
    } catch (e: any) {
      this.renderStatus("err", e?.message ?? String(e));
      new Notice(`Noosphere sync failed: ${e?.message ?? e}`);
    } finally {
      this.syncing = false;
    }
  }

  /**
   * The actual sync phases. Separate from syncNow() so error handling and
   * status bar concerns live at one level up.
   */
  private async runSyncPhases(
    client: NoosphereClient,
    opts: { corpusId: string; prune: boolean; writeback: boolean }
  ): Promise<{
    created: number;
    updated: number;
    unchanged: number;
    pruned: number;
    writeback: { written: number; skippedConflict: number } | null;
  }> {
    const { corpusId, prune, writeback } = opts;

    // ── Phase 1: enumerate + hash local files ─────────────────────────
    const localFiles = this.app.vault
      .getMarkdownFiles()
      .filter((f) => isWatched(f.path));
    const localMap = new Map<string, { file: TFile; hash: string; content: string }>();
    for (const f of localFiles) {
      const content = await this.app.vault.cachedRead(f);
      const hash = await sha256Hex(content);
      localMap.set(f.path, { file: f, hash, content });
    }

    // ── Phase 2: fetch server state, diff ─────────────────────────────
    const serverState = await client.getSyncState(corpusId);
    const serverMap = new Map<string, { hash: string; id: string }>();
    for (const d of serverState.docs) {
      serverMap.set(d.path, { hash: d.content_hash, id: d.id });
    }

    const toUpsert: { path: string; content: string }[] = [];
    for (const [path, info] of localMap) {
      const serverEntry = serverMap.get(path);
      if (!serverEntry || serverEntry.hash !== info.hash) {
        toUpsert.push({ path, content: info.content });
      }
    }
    const toDelete: string[] = [];
    if (prune) {
      for (const path of serverMap.keys()) {
        if (!localMap.has(path)) toDelete.push(path);
      }
    }

    // ── Phase 3: push upserts + deletes ───────────────────────────────
    let created = 0;
    let updated = 0;
    let unchanged = localFiles.length - toUpsert.length;
    for (const u of toUpsert) {
      try {
        const r = await client.upsertDoc(corpusId, u);
        if (r.action === "created") created++;
        else if (r.action === "updated") updated++;
        else if (r.action === "unchanged") unchanged++;
      } catch (e) {
        // Keep going — a single bad file shouldn't abort the whole sync.
        console.warn("Noosphere upsert failed for", u.path, e);
      }
    }
    let pruned = 0;
    for (const path of toDelete) {
      try {
        const r = await client.deleteDoc(corpusId, path);
        if (r.deleted) pruned++;
      } catch (e) {
        console.warn("Noosphere delete failed for", path, e);
      }
    }

    // ── Phase 4: writeback (client-side write, conflict-safe) ─────────
    let wbResult: { written: number; skippedConflict: number } | null = null;
    if (writeback) {
      wbResult = await this.applyWriteback(client, corpusId);
    }

    return {
      created,
      updated,
      unchanged,
      pruned,
      writeback: wbResult,
    };
  }

  /**
   * Pull synthesized entity/concept pages from the server and mirror them
   * into <vault>/__noosphere/. Idempotent; hashes stored in plugin state
   * detect local edits so user changes aren't overwritten — same contract
   * as the CLI's writeback path.
   */
  private async applyWriteback(
    client: NoosphereClient,
    corpusId: string
  ): Promise<{ written: number; skippedConflict: number }> {
    const since = this.state.writebackSeenAt ?? "";
    const payload = await client.getWriteback(corpusId, since);
    const hashes: Record<string, string> = { ...(this.state.writebackHashes ?? {}) };
    const adapter = this.app.vault.adapter;

    let written = 0;
    let skippedConflict = 0;

    for (const f of payload.files) {
      const relPath = normalizePath(`${WRITEBACK_ROOT}/${f.path}`);
      const newHash = await sha256Hex(f.content);

      const exists = await adapter.exists(relPath);
      if (exists) {
        const currentOnDisk = await adapter.read(relPath);
        const currentHash = await sha256Hex(currentOnDisk);
        const lastWritten = hashes[f.path];
        if (lastWritten && currentHash !== lastWritten) {
          // User edited it — don't overwrite.
          skippedConflict++;
          continue;
        }
        if (currentHash === newHash) {
          hashes[f.path] = newHash;
          continue;
        }
      } else {
        // Ensure parent directory exists before writing. Obsidian's adapter
        // raises if the directory isn't there for nested paths.
        const parent = relPath.substring(0, relPath.lastIndexOf("/"));
        if (parent && !(await adapter.exists(parent))) {
          await adapter.mkdir(parent);
        }
      }
      await adapter.write(relPath, f.content);
      hashes[f.path] = newHash;
      written++;
    }

    this.state.writebackSeenAt = payload.generated_at || this.state.writebackSeenAt;
    this.state.writebackHashes = hashes;
    await this.saveSettings();

    return { written, skippedConflict };
  }

  renderStatus(state: "idle" | "syncing" | "ok" | "err", detail?: string): void {
    if (!this.statusBarEl) return;
    const parts: string[] = ["Noosphere"];
    if (state === "syncing") parts.push("· syncing…");
    else if (state === "ok" && detail) parts.push("· " + detail);
    else if (state === "err") parts.push("· error");
    else if (this.settings.lastSyncAt) {
      const mins = Math.floor((Date.now() - new Date(this.settings.lastSyncAt).getTime()) / 60000);
      parts.push(mins < 1 ? "· just synced" : `· synced ${mins}m ago`);
    } else {
      parts.push("· not synced");
    }
    this.statusBarEl.setText(parts.join(" "));
    this.statusBarEl.title = detail ?? "";
    this.statusBarEl.removeClass("noos-status-err");
    this.statusBarEl.removeClass("noos-status-syncing");
    if (state === "err") this.statusBarEl.addClass("noos-status-err");
    if (state === "syncing") this.statusBarEl.addClass("noos-status-syncing");
  }
}
