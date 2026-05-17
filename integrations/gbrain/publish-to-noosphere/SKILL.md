# Publish to Noosphere

Your repo stays the source of truth. Noosphere makes this brain discoverable
and queryable by any agent, lets it learn from other brains on the network
(updates land only with your approval), and keeps it private, open, or paid.

Noosphere maps a gbrain repo at full fidelity:

- `people/` and `companies/` pages become **entity pages** — the compiled
  truth (above the `---`) becomes the entity's description; the timeline
  stays searchable.
- `concepts/` pages become **Wiki concept pages**.
- `meetings/`, `ideas/`, `deals/`, `projects/`, `sources/`, ... become
  **source documents**.
- gbrain cross-page slug links (`[text](../people/foo.md)`, `[[foo]]`)
  resolve to entity references.
- `index.md`, `log.md`, `RESOLVER.md`, `schema.md`, `.raw/`, `archive/`
  are skipped.

Everything imports as `source_kind=user_original` — this is the user's own
brain.

## Steps

1. **Find the brain root** — the directory that directly contains `people/`,
   `companies/`, `concepts/`, etc. Call it `BRAIN_DIR`.

2. **Read the publish marker** if it exists: `BRAIN_DIR/.noosphere.json`.
   - If present, this brain was already published. Use its `corpus_id` and
     `endpoint` for an incremental re-publish (step 4b).
   - If absent, this is a first publish (step 4a).

3. **Pick an access level** with the user. Default `private`. Options:
   `private` (only you), `public` (anyone/any agent, free), `paid`
   (agents pay per query or subscription — configure pricing in Noosphere
   after publishing). Call it `ACCESS`.

4. **Publish.**

   Prefer the local CLI (gbrain users are CLI-native). Noosphere is not
   on PyPI yet — ensure the `noosphere` command exists by running from
   source: `git clone https://github.com/steveyeow/noosphere.git && cd
   noosphere && pip install -e .` (installs deps + the CLI entry point).
   If `noosphere` still isn't on PATH, use `python -m noosphere.cli`
   instead of `noosphere` in the commands below.

   4a. **First publish** (no marker):

   ```
   noosphere connect-gbrain "$BRAIN_DIR" --name "<brain name>" --access-level "$ACCESS"
   ```

   This creates a corpus, imports the brain, indexes it, and — if the
   access level is not `private` — publishes it to the network. It prints
   a corpus ID.

   4b. **Re-publish** (marker exists, `corpus_id` known):

   ```
   noosphere import-gbrain "$BRAIN_DIR" --corpus "<corpus_id>"
   ```

   This re-imports changed pages into the existing corpus.

5. **Write/update the marker** `BRAIN_DIR/.noosphere.json` so future runs
   are incremental:

   ```json
   { "corpus_id": "<id from step 4>", "access_level": "<ACCESS>", "endpoint": "local" }
   ```

6. **(Network) serve for agents.** If `ACCESS` is not `private`, tell the
   user how to keep it reachable on the network:

   ```
   noosphere serve --public-url https://<your-host>
   ```

   The node auto-registers in the Noosphere registry on start and after
   every change.

7. **Report** the import result: number of entities, concept pages,
   sources, and cross-links resolved, plus the corpus ID and (if served)
   the public URL.

## Hosted Noosphere (no self-host)

If the user has a hosted Noosphere account instead of running their own
node:

1. Get an API token and the corpus ID from the Noosphere web app (create a
   corpus there once).
2. Zip the brain root and upload:

   ```
   cd "$BRAIN_DIR" && zip -r /tmp/brain.zip . -x '.git/*'
   curl -sS -F "file=@/tmp/brain.zip" \
     -H "Authorization: Bearer $NOOSPHERE_TOKEN" \
     "$NOOSPHERE_URL/api/v1/corpora/$CORPUS_ID/import/gbrain"
   ```

3. Write the marker with `"endpoint": "$NOOSPHERE_URL"` and the corpus ID.

## Notes

- Re-running is safe: entities dedupe by (kind, name); unchanged pages are
  skipped on re-index.
- The brain repo remains the system of record. Noosphere is the network,
  access-control, and monetization layer on top — it never writes back to
  the repo unless the user explicitly runs Noosphere writeback.
