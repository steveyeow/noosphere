# GBrain → Noosphere

Bring an existing [gbrain](https://github.com/garrytan/gbrain) brain onto the
Noosphere network. Your repo stays the source of truth. Noosphere makes that
brain discoverable and queryable by any agent, lets it learn from other
brains on the network (updates land only with your approval), and keeps it
private, open, or paid.

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
# Set up Noosphere (not on PyPI yet — run from source; pip install -e .
# pulls deps from pyproject and creates the `noosphere` command).
git clone https://github.com/steveyeow/noosphere.git
cd noosphere && pip install -e .

# First time: create a corpus, import, and (if not private) publish.
noosphere connect-gbrain ~/brain --name "My Brain" --access-level public

# Later, after the brain changes:
noosphere import-gbrain ~/brain --corpus <corpus_id>

# Serve it for agents on the network:
noosphere serve --public-url https://your-host
```

## Use it as a gbrain skill (one command)

So the brain can publish itself — and re-publish whenever it grows. Run
this **from your gbrain repo root** (needs `jq`):

```bash
NS=https://raw.githubusercontent.com/steveyeow/noosphere/main/integrations/gbrain
mkdir -p skills/publish-to-noosphere \
 && curl -fsSL $NS/publish-to-noosphere/SKILL.md -o skills/publish-to-noosphere/SKILL.md \
 && jq --argjson e "$(curl -fsSL $NS/manifest-entry.json)" \
      '.skills += [$e]' skills/manifest.json > skills/manifest.json.tmp \
 && mv skills/manifest.json.tmp skills/manifest.json
```

Then ask your agent: **run the publish-to-noosphere skill**. It finds the
brain root, imports it into Noosphere, writes a `.noosphere.json` marker
for incremental re-publishing, and reports what mapped.

No `jq`? Copy `publish-to-noosphere/SKILL.md` into `skills/` and paste the
object from [`manifest-entry.json`](manifest-entry.json) into the `skills`
array of your `skills/manifest.json`.

To get it shipped to every gbrain user by default, see
[`SUBMISSION.md`](SUBMISSION.md) — a ready-to-file proposal for the
upstream `garrytan/gbrain` skill catalog.

## Hosted Noosphere

No self-host required — create a corpus in the Noosphere web app, then:

```
cd ~/brain && zip -r /tmp/brain.zip . -x '.git/*'
curl -sS -F "file=@/tmp/brain.zip" \
  -H "Authorization: Bearer $NOOSPHERE_TOKEN" \
  "$NOOSPHERE_URL/api/v1/corpora/$CORPUS_ID/import/gbrain"
```
