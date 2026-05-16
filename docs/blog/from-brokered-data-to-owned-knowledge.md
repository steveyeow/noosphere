# From Made-to-Order Data to Owned Knowledge

*2026-05-16 — Noosphere*

How the scarce input to AI inverted from public text to owned human knowledge — what agents actually need from it, who should own it, and the market that replaces the broker.

The economics of training data have quietly inverted. For a decade the constraint
on machine intelligence was compute and architecture; the data was a free
externality you scraped off the open web. That era is closing. The most-cited
public corpora are now litigated shut to commercial training, the open web is
increasingly polluted with model output, and the highest-quality public text is
running out. At the same time the frontier moved to model classes — embodied
agents, computer-use agents, voice systems, domain reasoners — that need data the
web never contained: first-person recordings of real work, real conversations,
and the tacit judgment that lives only in people's heads.

So the scarce input is no longer text. It is real human knowledge, captured with
clean rights. That single shift turns a technical question into a question about
property: who owns what individuals know, who gets to price it, and through what
mechanism it changes hands. This is an essay about that question, and about the
shape of the answer we think is correct.

## Three ways to supply knowledge

There are two dominant structures for getting human knowledge to a model today,
and a third one is now becoming possible.

The first is **captured**. People create for their own reasons — to talk, to
learn, to work in public, to find an audience — and platforms capture the asset.
This was the social-media supply line for AI: human production, taken in bulk,
with no payment to the creator and increasingly murky rights. It worked while
public text was abundant and cheap. That era is ending.

The second is **made to order**. A lab writes a specification. A vendor recruits
people to fulfill it, runs them through review, and delivers a dataset, often
exclusively, to the buyer who ordered it. This is how the current data market
works, and it is a real business. But it has a structural cost that is easy to
miss: information is naturally non-rival — one person's use of a fact does not
consume it — yet a made-to-order, exclusive deal *re-imposes* rivalry on it so
the sale can be made legible. The buyer pays for exclusivity; the data is sold
once; its reuse value is deliberately destroyed to make the transaction clean.
Every new need re-incurs the full collection cost.

The third is **owned and living**. People and teams keep producing knowledge
anyway — in notes, research, chats, operating documents, customer calls,
experiments, and future agent-facing work. Noosphere's premise is that this
continuous first-party production should stay with the person or organization
that made it, then optionally become accessible to agents under terms the owner
sets. Nobody is dispatched to fulfill a buyer's spec, which is the operating
model of data vendors (Scale, Surge, Mercor, Luel). That single difference —
*owned, self-motivated production* versus *assignment fulfillment* — is the line
this whole essay is about. The same corpus can be licensed to many consumers
with no re-collection and no exclusivity entanglement, because its natural
non-rivalry was never bargained away.

The difference is not a matter of taste. An owned-supply market preserves a
property of information that the made-to-order market spends money to destroy.
That is a structural efficiency, and it compounds: each published body of
knowledge is simultaneously available to every consumer who needs it, and grows
more valuable as it deepens rather than being consumed by its first sale.

## What an agent actually needs

It is tempting to assume agents consume knowledge the way people do. They do not,
and the difference dictates the entire design.

When a person reads a source, they verify it internally. They judge the author,
weigh the claim against what they know, and decide how much to trust it. The
verification happens inside the reader and never has to leave.

An agent cannot do this. It folds external knowledge into an output that its
principal — a company, a developer, a user — is accountable for, and it has no
way to discharge that accountability internally. An unattributed assertion is a
liability it cannot accept. This is the keystone: **an agent must externalize
the verification a human performs internally.** Almost every requirement follows
from it.

- It needs to decide relevance *before* spending money or compute, so a source
  must be machine-describable and previewable.
- It needs resolution at the level of the **claim**, not the document — the
  minimal sufficient answer to a specific question, each claim independently
  traceable. The document is a human's unit of consumption; the claim is an
  agent's.
- It needs **verifiable provenance** per claim, because the liability for a
  wrong claim transfers to it.
- It needs **honest calibration and honest scope**. A confident wrong answer
  poisons the agent's reasoning chain, which makes an honest "I do not cover
  this" more valuable than a vague attempt.
- It needs **temporal validity** — as of when a claim holds, and whether it has
  been superseded — because it has to reason about staleness.
- It needs a **machine-legible license and price**. License terms are not
  compliance overhead; they are part of usability. An agent that cannot
  mechanically determine what it is permitted to do with an answer cannot safely
  use the answer at all.

Stated plainly: for an agent, usable knowledge is a verifiable, attributable,
scoped, time-stamped, license-legible claim — not a file. Any knowledge layer
built for agents has to produce that, or it is not really for agents.

## Knowledge as personal property

If individual human knowledge is now the scarce input to machine intelligence,
then the question of who owns it is not academic. The made-to-order market
answers it by default: the vendor intermediates, the buyer orders, and the person
whose knowledge it is appears only as paid labor at the bottom of the stack. The
rights, the catalog, and the compounding margin accrue to the intermediary.

We think the correct default is the opposite. The person who created the
knowledge owns it. They decide whether it is private, shared freely, or priced.
They keep the revenue. Provenance and consent live at the source — recorded when
the knowledge enters, not reconstructed by a vendor afterward — because the only
moment you can capture origin losslessly is the moment of creation. And only
content a person actually originated is monetizable: imported third-party
material is filtered out for paying consumers, so the market cannot become a
laundering channel for other people's copyrighted work. Creator sovereignty and
anti-laundering turn out to be the same rule.

This is what "personal knowledge rights" means concretely. Not a slogan about
ownership, but a set of mechanisms: attribution attached at ingest, a license
the owner sets and the buyer can read, a hard rule that you can only sell what
is yours, and revenue that flows to the person rather than the broker. In
Noosphere these are real surfaces — per-document `source_kind` attribution, a
machine-readable manifest, the rule that only user-originated content is served
to paying callers, and direct payment that the platform never sits in the middle
of for self-hosted creators.

## A market, not a broker

The made-to-order model needs a human in the middle because supply starts with a
buyer request: someone specifies, someone recruits, someone fulfills. Owned
supply removes the reason for that middle. What replaces the broker is not a
smarter central matcher; it is **a shared, machine-decidable vocabulary on both
sides, plus a pull protocol.**

Concretely, automated matching needs three things. A consuming agent must be
able to state its need in the same vocabulary a knowledge base uses to describe
itself — task type, topic, and the provenance, calibration, freshness, and
license constraints it requires. The knowledge base must be able to answer, in a
typed way, whether it can satisfy that need and at what confidence — including an
honest no. And settlement must close without a human: autonomous payment, plus a
reputation signal that accumulates *per kind of need*, so the market learns
which sources satisfy which needs over time. That accumulated mapping is the
thing that replaces the broker's matching judgment.

The primitives for this already exist in the product: a `describe` manifest as
the supply-side self-description, `preview_ask` so an agent can evaluate a paid
source before paying, a `kb_reputation` that accrues from real citations and
real return usage rather than promotion, and an x402 payment path so an agent
can settle without a browser or a card form. The missing half — and the honest
statement of where the work is — is the symmetric demand-side object: the spec
an agent carries, against which a source reports conformance. Matching is
two-sided; today only one side speaks. Closing that gap is what turns a
well-described supply into an actual market.

## How it is consumed

It is easy to read "owned knowledge for AI" as a training-data play. Primarily,
it is not. The native mode is runtime: an agent, mid-task, calls a knowledge
base the way it calls any tool, uses the answer in context, and never trains on
it — an open-book lookup paid per call, not material absorbed into weights. The
same owned, non-rival supply can additionally be licensed in bulk for
post-training or pre-training, because non-rivalry lets one corpus serve every
mode at once — but those are a licensing adjacency on top of the runtime layer,
not the center. The distinction is load-bearing: a runtime answer keeps its
provenance and citation live at the moment of use; once knowledge is absorbed
into weights, that link is gone. Designing for the runtime case is exactly what
forces the verifiable, attributable, license-legible claim described above.

## What this asks of the tools

The hard part is not the market mechanism. It is making the act of building
knowledge *for yourself* emit, as a byproduct, the structure an accountable
consumer needs — without the user ever working for the buyer, and without
distorting their knowledge toward whatever pays.

That is a design constraint, and it points somewhere specific. Provenance and
the author's epistemic stance should be encoded by *which way knowledge enters* —
writing an original note is a different act from connecting an external feed, and
the system should treat them differently rather than flattening them into
"content." Synthesis should not summarize; it should convert what a person knows
into attributed, scoped, time-stamped claims. The tacit context that self-written
knowledge always omits — the assumptions, the boundary conditions, the "why" —
should be drawn out conversationally, framed honestly as making your own
knowledge sharper, because decontextualized knowledge is in fact more useful to
your own future self and your own agents, not only to a buyer. Scope and
uncertainty should be computed from what the corpus actually contains, not
self-declared, so honesty is structural rather than requested.

None of this is built because monetization needs it. It is built because it is
what knowledge should be once it has to be read by something that carries the
weight of being wrong. The market is a consequence, not the goal.

The goal is older and simpler: a commons of human knowledge that is owned by the
people who made it, that compounds instead of decaying, and that is paid for at
the source. The web indexed knowledge for human attention, where popular and
valuable came apart. Agents do not pay an attention tax; they select for
informational value and verifiable provenance. The platform shape that fits that
selection is one where the person keeps the rights, the knowledge keeps growing,
and anything that reads it — human or agent — can see exactly where it came from.
