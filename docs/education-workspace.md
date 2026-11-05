# Generated education copy and professional review (#17)

`/education` is separate from `/knowledge`: approved source versions are evidence, while generated
education copy starts as a private `draft`. The workspace accepts an authorized branch, department,
topic and up to ten current approved source versions. It preserves source/version/checksum/chunk
snapshots and stable `[來源1]` references. Source contents and topics are untrusted data in the generation
prompt. AI output is never automatically published or inserted into the source corpus.

The API lives under `/api/education`:

- `POST /drafts`: generate a pending copy from explicit approved sources; recheck after the model call.
- `GET /drafts`, `GET /drafts/{id}`: staff work queue/history, or only published accessible copy for readers.
- `POST /drafts/{id}/revisions`: append an immutable human revision with unified diff, actor, time and reason.
- `POST /drafts/{id}/transition`: submit, return, approve-and-publish, withdraw. Every operation records an event.
- `POST /feedback`: report an accessible source or an owned conversation that actually cited the source.
- `GET /feedback`: Reviewer/Admin feedback queue, with version and conversation trace IDs.

Nurse may generate/edit/submit. Reviewer/Admin may return, approve and withdraw. Every mutation includes
`expected_revision`, rejecting stale tabs rather than overwriting edits. In-review/published copy cannot be
edited; a returned draft may be revised. Publishing requires current source authorization/validity and an
explicit professional review reason. Citation-number validation is syntactic, not a semantic support score.
A reviewer must check every paragraph before publication. Published text may retain the generated draft
heading; the authoritative publication state and approval actor/time are separate metadata.

Reader accounts cannot retrieve unapproved copy, internal revisions, diffs or full evidence snapshots.
Source named-user ACLs apply to staff snapshots as well. When a source expires, is withdrawn or superseded,
its generated published copy becomes unavailable to readers. Staff with source access can still audit it.
An owner may report an earlier conversation's withdrawn citation without regaining access to source text.
Feedback must omit personal health data. Query IDs currently refer to private conversation records; complete
immutable query traces and experiment snapshots belong to #19.

## Synthetic check-preparation e2e

Use synthetic sources describing only appointment-location checks and bringing a notice (not real clinical
preparation instructions). Select them, set topic `檢查前衛教`, generate, add an explicit synthetic-use note,
save a revision, submit, return, edit/resubmit, approve, then withdraw. Compare r1/r2, original evidence IDs,
review events and reader visibility at each step. Backend tests cover this lifecycle, stale revisions,
missing/invalid citation IDs, cross-organization/scope/named-user ACLs, concurrent source withdrawal during
generation and owned-query feedback. Model outputs are mocked in regression tests, not graded as clinical
facts. The preview demo also exercises a real GPT-6 Luna generation with synthetic content.
