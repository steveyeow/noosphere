/**
 * Thin HTTP wrapper for the Noosphere REST API.
 *
 * Cloud-safe by design — every endpoint sends file CONTENT, not
 * filesystem paths. Works identically whether the server is local
 * (http://localhost:8420) or cloud (app.noosphere.wiki).
 *
 * Four calls in the sync lifecycle:
 *   - getCorpus()          — liveness + corpus info for the test button
 *   - getSyncState()       — server's (path → hash) map, for client-side diff
 *   - upsertDoc()          — push one file
 *   - deleteDoc()          — prune one file
 *   - getWriteback(since)  — pull synthesized entity/concept pages
 *
 * The legacy syncLocal() is kept for backwards compatibility with
 * Noosphere instances where the server and Obsidian share a filesystem;
 * new code should use the per-document path so it works everywhere.
 */

export type CorpusInfo = {
  id: string;
  slug: string;
  name: string;
  document_count?: number;
  chunk_count?: number;
};

export type SyncStateDoc = {
  path: string;
  content_hash: string;
  id: string;
  title: string;
};

export type SyncStateResponse = {
  corpus_id: string;
  docs: SyncStateDoc[];
};

export type UpsertResult = {
  id: string | null;
  action: "created" | "updated" | "unchanged" | "skipped";
  title: string;
};

export type WritebackFile = {
  path: string;
  content: string;
  updated_at: string;
  kind: "entity" | "concept";
};

export type WritebackResponse = {
  corpus_id: string;
  generated_at: string;
  since: string;
  files: WritebackFile[];
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

  private async fetchJson<T>(path: string, init: RequestInit = {}): Promise<T> {
    const url = this.baseUrl.replace(/\/+$/, "") + path;
    const r = await fetch(url, { ...init, headers: this.headers(init.headers as any) });
    if (!r.ok) {
      let detail = "";
      try {
        detail = await r.text();
      } catch {}
      throw new Error(`${init.method || "GET"} ${path} failed (${r.status}): ${detail}`);
    }
    return (await r.json()) as T;
  }

  async getCorpus(corpusId: string): Promise<CorpusInfo> {
    return this.fetchJson(`/api/v1/corpora/${encodeURIComponent(corpusId)}`);
  }

  /** Create a new corpus. Used by the plugin's "Create new corpus" button
   *  so users don't have to jump to the web UI for first-time setup. */
  async createCorpus(args: {
    name: string;
    description?: string;
    tags?: string[];
    access_level?: "public" | "private" | "token" | "paid";
  }): Promise<CorpusInfo> {
    return this.fetchJson(`/api/v1/corpora`, {
      method: "POST",
      body: JSON.stringify({
        name: args.name,
        description: args.description ?? "",
        tags: args.tags ?? [],
        access_level: args.access_level ?? "private",
      }),
    });
  }

  async getSyncState(corpusId: string): Promise<SyncStateResponse> {
    return this.fetchJson(`/api/v1/corpora/${encodeURIComponent(corpusId)}/sync/state`);
  }

  async upsertDoc(
    corpusId: string,
    args: { path: string; content: string; format?: string }
  ): Promise<UpsertResult> {
    return this.fetchJson(`/api/v1/corpora/${encodeURIComponent(corpusId)}/sync/upsert`, {
      method: "POST",
      body: JSON.stringify({
        path: args.path,
        content: args.content,
        format: args.format ?? "obsidian",
      }),
    });
  }

  async deleteDoc(corpusId: string, path: string): Promise<{ deleted: boolean }> {
    return this.fetchJson(
      `/api/v1/corpora/${encodeURIComponent(corpusId)}/sync/doc?path=${encodeURIComponent(path)}`,
      { method: "DELETE" }
    );
  }

  async getWriteback(corpusId: string, since: string = ""): Promise<WritebackResponse> {
    const q = since ? `?since=${encodeURIComponent(since)}` : "";
    return this.fetchJson(
      `/api/v1/corpora/${encodeURIComponent(corpusId)}/writeback${q}`
    );
  }
}

/** SHA-256 of a string, lowercase hex. Used for client-side hash diff
 *  against the server's sync/state payload. Matches Python's
 *  hashlib.sha256(text.encode("utf-8")).hexdigest(). */
export async function sha256Hex(text: string): Promise<string> {
  const buf = new TextEncoder().encode(text);
  const digest = await crypto.subtle.digest("SHA-256", buf);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}
