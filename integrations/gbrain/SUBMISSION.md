# Upstream submission draft — `publish-to-noosphere` skill for gbrain

A ready-to-file proposal for the [`garrytan/gbrain`](https://github.com/garrytan/gbrain)
skill catalog. Submit it as a PR/issue if/when the gbrain project accepts
community skills. Keep it value-first and concise — it's a request to an
external maintainer, not a marketing drop.

---

## Suggested PR title

`Add publish-to-noosphere skill (optional: share/serve a brain to the agent network)`

## Suggested PR body

> Adds one optional skill, `publish-to-noosphere`, that lets a brain
> publish itself to [Noosphere](https://github.com/steveyeow/noosphere) —
> an open network where a brain becomes agent-queryable and, if the owner
> chooses, access-controlled or paid. The gbrain repo stays the system of
> record; nothing about the local workflow changes.
>
> It's strictly additive and opt-in:
> - One folder, `skills/publish-to-noosphere/SKILL.md`
> - One entry appended to `skills/manifest.json`
> - No new dependencies, no changes to existing skills, no network calls
>   unless a user explicitly runs the skill
>
> The mapping is faithful to gbrain's model (zero-LLM, derived from page
> structure): `people/` + `companies/` → entity pages (compiled truth
> becomes the entity description), `concepts/` → wiki pages, cross-page
> slug links → typed relationship edges. Re-runnable and incremental via
> a `.noosphere.json` marker.
>
> Happy to adjust naming, scope, or wording to fit the catalog's
> conventions.

## Files in this PR

```
skills/publish-to-noosphere/SKILL.md      # from integrations/gbrain/publish-to-noosphere/SKILL.md
skills/manifest.json                       # append the object below to .skills[]
```

Manifest entry to append (also in [`manifest-entry.json`](manifest-entry.json)):

```json
{
  "name": "publish-to-noosphere",
  "path": "publish-to-noosphere/SKILL.md",
  "description": "Publish this brain to the Noosphere network — agent-discoverable, access-controlled, optionally paid. people/companies become entity pages, concepts become Wiki pages; the repo stays the system of record."
}
```

## Notes for the submitter

- Do **not** open this PR from automation. A human should file it, engage
  with the maintainer, and accept their conventions.
- If the project does not take community skills, the same skill still works
  via the one-command install in [`README.md`](README.md) — distribution
  does not depend on upstream acceptance, it just compounds with it.
