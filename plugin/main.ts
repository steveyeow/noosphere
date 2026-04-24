/**
 * Noosphere plugin — Obsidian entry point.
 *
 * Three user-facing affordances:
 *   1. Ribbon icon + command palette entry for "Sync now"
 *   2. Status bar item showing last sync summary
 *   3. Settings tab (URL, corpus, token, toggles — see settings.ts)
 *
 * Watch mode hooks into vault mtime events (create/modify/delete on
 * `.md` files outside __noosphere/ and .obsidian/). Changes are batched
 * into a debounced sync call so a quick burst of saves triggers ONE sync,
 * not N.
 *
 * The plugin is intentionally thin — it's a UX layer on top of the
 * server's /sync-local endpoint, which does all the real work (walking
 * the vault, diffing against the corpus, posting updates, writeback).
 * Designed so that if you stop using the plugin, the CLI keeps working
 * on the exact same vault.
 */

import { FileSystemAdapter, Notice, Plugin, TFile, debounce } from "obsidian";
import { NoosphereClient } from "./client";
import { DEFAULT_SETTINGS, NoosphereSettings, NoosphereSettingTab } from "./settings";

export default class NoospherePlugin extends Plugin {
  settings!: NoosphereSettings;
  statusBarEl: HTMLElement | null = null;
  private vaultPath: string | null = null;
  // Debounced sync lives on the instance so we can swap it when the
  // watch-mode toggle flips (creating a new debouncer is cheaper than
  // reasoning about whether the old one is cancelled).
  private debouncedSync: ((reason: string) => void) | null = null;
  private vaultEventRefs: any[] = [];
  private syncing = false;

  async onload(): Promise<void> {
    await this.loadSettings();

    // Compute the vault's absolute path on disk. Desktop-only; the
    // plugin's manifest marks it isDesktopOnly so this cast is safe.
    const adapter = this.app.vault.adapter;
    if (adapter instanceof FileSystemAdapter) {
      this.vaultPath = adapter.getBasePath();
    }

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
        // Obsidian's setting pane is opened programmatically via an
        // internal method; narrow call surface keeps us resilient to
        // minor API reshuffles.
        (this.app as any).setting.open();
        (this.app as any).setting.openTabById("noosphere-sync");
      },
    });

    this.addSettingTab(new NoosphereSettingTab(this.app, this));

    // Start in watch mode if the user had it on. No initial sync fires
    // automatically — the user opts in via ribbon / command / watch.
    this.updateWatchMode();
  }

  onunload(): void {
    this.disableWatchMode();
  }

  async loadSettings(): Promise<void> {
    this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
  }

  async saveSettings(): Promise<void> {
    await this.saveData(this.settings);
  }

  updateWatchMode(): void {
    this.disableWatchMode();
    if (!this.settings.watchMode) return;

    // Debounce batches rapid saves (e.g. mass find-and-replace) into
    // one sync call. 1500ms feels responsive without being chatty.
    this.debouncedSync = debounce(
      (reason: string) => this.syncNow(reason),
      1500,
      true
    );

    const isWatched = (path: string) => {
      if (!path.toLowerCase().endsWith(".md")) return false;
      const parts = path.split("/");
      // Mirror the server-side skip rules so watch events for files
      // that will be filtered out don't trigger pointless syncs.
      if (parts.some((p) => p.startsWith("."))) return false;
      if (parts.some((p) => p === "__noosphere")) return false;
      return true;
    };

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
    if (!this.vaultPath) {
      new Notice("Noosphere: vault path unavailable (is this desktop?)");
      return;
    }
    this.syncing = true;
    this.renderStatus("syncing");
    try {
      const client = new NoosphereClient(serverUrl, apiToken);
      const result = await client.syncLocal(corpusId, {
        path: this.vaultPath,
        format: "obsidian",
        prune,
        writeback,
      });
      const s = result.sync;
      const wb = result.writeback;
      const wbStr = wb ? ` · wb ${wb.written}↓ ${wb.skipped_conflict}⊘` : "";
      const msg = `${s.new} new · ${s.updated} upd · ${s.unchanged} same${s.pruned ? " · " + s.pruned + " pruned" : ""}${wbStr}`;
      this.settings.lastSyncAt = new Date().toISOString();
      await this.saveSettings();
      this.renderStatus("ok", msg);
      // Only notify on meaningful activity so watch-mode syncs don't
      // spam the user.
      if (s.new || s.updated || s.pruned || (wb && wb.written)) {
        new Notice(`Noosphere: ${msg}`);
      }
    } catch (e: any) {
      this.renderStatus("err", e?.message ?? String(e));
      new Notice(`Noosphere sync failed: ${e?.message ?? e}`);
    } finally {
      this.syncing = false;
    }
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
