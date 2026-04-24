/**
 * Thin HTTP wrapper for the Noosphere REST API.
 *
 * The plugin's primary call is POST /corpora/{id}/sync-local which drives
 * the server-side sync_directory against a filesystem path. This assumes
 * Noosphere is running on the same machine as Obsidian (the Karpathy
 * self-hosted setup). Cloud Noosphere would need file-upload endpoints;
 * scoped out of v0.1 but the client is designed to accept either URL.
 */

export type SyncLocalResult = {
  sync: { new: number; updated: number; unchanged: number; pruned: number };
  index: { chunk_count?: number } | null;
  writeback: { written: number; skipped_conflict: number } | null;
};

export type CorpusInfo = {
  id: string;
  slug: string;
  name: string;
  document_count?: number;
  chunk_count?: number;
};

export class NoosphereClient {
  constructor(private baseUrl: string, private token: string = "") {}

  private headers(extra: Record<string, string> = {}): Record<string, string> {
    const h: Record<string, string> = {
      "Content-Type": "application/json",
      ...extra,
    };
    if (this.token) h["Authorization"] = `Bearer ${this.token}`;
    return h;
  }

  private async fetch(path: string, init: RequestInit = {}): Promise<Response> {
    const url = this.baseUrl.replace(/\/+$/, "") + path;
    const r = await fetch(url, { ...init, headers: this.headers(init.headers as any) });
    return r;
  }

  /** Liveness + minimal corpus info fetch. Used on connect-test. */
  async getCorpus(corpusId: string): Promise<CorpusInfo> {
    const r = await this.fetch(`/api/v1/corpora/${encodeURIComponent(corpusId)}`);
    if (!r.ok) throw new Error(`Corpus lookup failed (${r.status}): ${await r.text()}`);
    return r.json();
  }

  /** Trigger a local-filesystem sync on the server. */
  async syncLocal(
    corpusId: string,
    opts: { path: string; format?: string; prune?: boolean; writeback?: boolean }
  ): Promise<SyncLocalResult> {
    const body = JSON.stringify({
      path: opts.path,
      format: opts.format ?? "obsidian",
      prune: !!opts.prune,
      writeback: opts.writeback !== false,
    });
    const r = await this.fetch(`/api/v1/corpora/${encodeURIComponent(corpusId)}/sync-local`, {
      method: "POST",
      body,
    });
    if (!r.ok) {
      const detail = await r.text();
      throw new Error(`Sync failed (${r.status}): ${detail}`);
    }
    return r.json();
  }
}
