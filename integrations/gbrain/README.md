# GBrain → Noosphere

Bring an existing [gbrain](https://github.com/garrytan/gbrain) brain onto the
Noosphere network. The brain repo stays the system of record on disk;
Noosphere becomes the network, access-control, and monetization layer on top.

## What the adapter maps

A gbrain repo is a directory of markdown pages organized by typed folders,
each page being YAML frontmatter, then compiled truth, then a `---`, then an
append-only timeline. The Noosphere importer maps that at full fidelity:

| gbrain | Noosphere |
|---|---|
| `people/<slug>.md` | entity, `kind=person`, description = compiled truth |
| `companies/<slug>.md` | entity, `kind=organization`, description = compiled truth |
| `concepts/<slug>.md` | `doc_type=concept` (Wiki section) |
| `meetings/` `ideas/` `deals/` `projects/` `sources/` ... | source documents |
| compiled truth (above `---`) | entity description / page truth |
| timeline (below `---`) | kept in the page document (searchable) |
| `[text](../people/x.md)`, `[[x]]` cross-links | resolved to entity references |
| `index.md` `log.md` `RESOLVER.md` `schema.md` `.raw/` `archive/` | skipped |

Everything imports as `source_kind=user_original`.

## Use it directly (CLI)

```
pipx install noosphere

# First time: create a corpus, import, and (if not private) publish.
noosphere connect-gbrain ~/brain --name "My Brain" --access-level public

# Later, after the brain changes:
noosphere import-gbrain ~/brain --corpus <corpus_id>

# Serve it for agents on the network:
noosphere serve --public-url https://your-host
```

## Use it as a gbrain skill

So a brain can publish itself (and re-publish whenever it grows):

1. Copy the `publish-to-noosphere/` folder into your gbrain repo's `skills/`
   directory.
2. Add the object in `manifest-entry.json` to the `skills` array in your
   gbrain `skills/manifest.json` (or run `gbrain skillpack install` if you
   package it as a skillpack).
3. Ask your agent to run the **publish-to-noosphere** skill. It finds the
   brain root, imports it into Noosphere, writes a `.noosphere.json` marker
   for incremental re-publishing, and reports what mapped.

## Hosted Noosphere

No self-host required — create a corpus in the Noosphere web app, then:

```
cd ~/brain && zip -r /tmp/brain.zip . -x '.git/*'
curl -sS -F "file=@/tmp/brain.zip" \
  -H "Authorization: Bearer $NOOSPHERE_TOKEN" \
  "$NOOSPHERE_URL/api/v1/corpora/$CORPUS_ID/import/gbrain"
```
