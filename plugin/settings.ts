/**
 * Settings tab for the Noosphere plugin. Minimal by design — the four
 * pieces of state a user needs to configure are:
 *   - Server URL (defaults to local Noosphere at :8420)
 *   - Corpus ID or slug (the destination KB)
 *   - API token (optional for self-hosted, required for cloud)
 *   - Behavior toggles: writeback, watch mode, prune
 *
 * Everything else is sensible defaults — when "it just works" conflicts
 * with "make it configurable", we err on "just works".
 */

import { App, PluginSettingTab, Setting, Notice } from "obsidian";
import type NoospherePlugin from "./main";
import { NoosphereClient } from "./client";

export interface NoosphereSettings {
  serverUrl: string;
  corpusId: string;
  apiToken: string;
  writeback: boolean;
  watchMode: boolean;
  prune: boolean;
  lastSyncAt: string;
}

export const DEFAULT_SETTINGS: NoosphereSettings = {
  serverUrl: "http://localhost:8420",
  corpusId: "",
  apiToken: "",
  writeback: true,
  watchMode: false,
  prune: false,
  lastSyncAt: "",
};

export class NoosphereSettingTab extends PluginSettingTab {
  plugin: NoospherePlugin;

  constructor(app: App, plugin: NoospherePlugin) {
    super(app, plugin);
    this.plugin = plugin;
  }

  display(): void {
    const { containerEl } = this;
    containerEl.empty();

    containerEl.createEl("h2", { text: "Noosphere" });
    const intro = containerEl.createEl("p", { cls: "noos-intro" });
    intro.setText(
      "Point this vault at a Noosphere corpus. The plugin sends the vault's filesystem path to your Noosphere server, which runs sync there. Self-hosted Noosphere on the same machine as Obsidian is the supported setup."
    );

    new Setting(containerEl)
      .setName("Server URL")
      .setDesc("Where your Noosphere is running. Default: local self-hosted at port 8420.")
      .addText((text) =>
        text
          .setPlaceholder("http://localhost:8420")
          .setValue(this.plugin.settings.serverUrl)
          .onChange(async (value) => {
            this.plugin.settings.serverUrl = value.trim();
            await this.plugin.saveSettings();
          })
      );

    new Setting(containerEl)
      .setName("Corpus ID or slug")
      .setDesc("The knowledge base this vault syncs into. Create it on the Noosphere web UI first.")
      .addText((text) =>
        text
          .setPlaceholder("my-knowledge")
          .setValue(this.plugin.settings.corpusId)
          .onChange(async (value) => {
            this.plugin.settings.corpusId = value.trim();
            await this.plugin.saveSettings();
          })
      );

    new Setting(containerEl)
      .setName("API token")
      .setDesc("Optional for self-hosted local Noosphere. Required when pointing at cloud Noosphere.")
      .addText((text) => {
        text.inputEl.type = "password";
        text
          .setPlaceholder("Paste token if needed")
          .setValue(this.plugin.settings.apiToken)
          .onChange(async (value) => {
            this.plugin.settings.apiToken = value.trim();
            await this.plugin.saveSettings();
          });
      });

    new Setting(containerEl)
      .setName("Writeback")
      .setDesc(
        "Mirror Noosphere-synthesized entity and concept pages into __noosphere/ after each sync. Local edits to those files are preserved."
      )
      .addToggle((t) =>
        t.setValue(this.plugin.settings.writeback).onChange(async (v) => {
          this.plugin.settings.writeback = v;
          await this.plugin.saveSettings();
        })
      );

    new Setting(containerEl)
      .setName("Watch mode")
      .setDesc(
        "Automatically trigger a sync a few seconds after every save. Turn off if you want manual control."
      )
      .addToggle((t) =>
        t.setValue(this.plugin.settings.watchMode).onChange(async (v) => {
          this.plugin.settings.watchMode = v;
          await this.plugin.saveSettings();
          this.plugin.updateWatchMode();
        })
      );

    new Setting(containerEl)
      .setName("Prune")
      .setDesc(
        "Remove documents from Noosphere when their source files disappear from the vault. Off by default — easier to recover accidents."
      )
      .addToggle((t) =>
        t.setValue(this.plugin.settings.prune).onChange(async (v) => {
          this.plugin.settings.prune = v;
          await this.plugin.saveSettings();
        })
      );

    new Setting(containerEl)
      .setName("Test connection")
      .setDesc("Checks that the server URL is reachable and the corpus exists.")
      .addButton((btn) =>
        btn.setButtonText("Test").onClick(async () => {
          const { serverUrl, corpusId, apiToken } = this.plugin.settings;
          if (!serverUrl || !corpusId) {
            new Notice("Server URL and corpus ID are required");
            return;
          }
          btn.setDisabled(true);
          try {
            const client = new NoosphereClient(serverUrl, apiToken);
            const info = await client.getCorpus(corpusId);
            new Notice(`Connected: "${info.name}" (${info.document_count ?? 0} docs)`);
          } catch (e: any) {
            new Notice(`Connect failed: ${e?.message ?? e}`);
          } finally {
            btn.setDisabled(false);
          }
        })
      );

    containerEl.createEl("h3", { text: "What gets synced" });
    const ul = containerEl.createEl("ul", { cls: "noos-bullets" });
    const bullets = [
      "Every .md note in your vault, respecting folder structure",
      "YAML frontmatter, #hashtags, and [[wikilinks]] (resolved to entities)",
      "Skipped: .obsidian/, .trash/, dotfiles, __noosphere/ (the writeback mirror)",
      "Attachments (images, PDFs) are not synced via this plugin — upload separately if needed",
    ];
    bullets.forEach((b) => ul.createEl("li").setText(b));
  }
}
