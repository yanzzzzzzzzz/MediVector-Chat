# Experiment snapshots, audit and release gates (#19)

## Reproducibility

Snapshots retain source/version/checksum/chunk IDs, corpus hash, embedding model/dimensions, configured
chat/query-expansion models, prompt-module hashes, retriever parameters, index strategy/version,
dataset version and Git SHA. A digest of actual runtime Python/migration files supplements Git identity. New generated drafts capture
their original generation parameters before the model call and preserve that snapshot through human
revisions. Publication captures its own current configuration separately; old drafts without generation
metadata stay explicitly unknown, rather than being attributed to a newer model.
External models are nondeterministic: snapshots reproduce inputs/configuration, not identical outputs.
Missing dataset/index/build metadata requires explicit review, never a fabricated verified baseline.

Docker builds accept `APP_GIT_SHA` as a build argument (Compose reads the same environment variable):

```sh
APP_GIT_SHA="$(git rev-parse HEAD)" docker compose --env-file .env build app
```

Use a clean checkout matching the SHA. Without it the container records `unknown`, plus its source hash;
there is no guessed SHA. A local checkout also records whether its working tree is dirty. Prompt versions
are SHA256 of the relevant runtime modules, rather than undocumented handwritten labels.

## Query traces and privacy

Institutional `/api/ask` returns `query_trace_id`. Owners can read
`GET /api/knowledge/query-traces/{id}` or list IDs with
`GET /api/knowledge/query-traces?conversation_id={id}`. Other accounts, including other staff, cannot read
private traces. The trace stores authorized reference IDs/ranks/distances, applied filters, a pre-query
corpus/configuration snapshot and elapsed time (excluding audit persistence). If the corpus changes while
the answer runs, the post-query corpus is also retained and the change flagged. `answer_model_invoked`
distinguishes canonical no-evidence refusal from generated answers.

The audit table does not copy raw questions, answers, rewrite terms, source text or API credentials.
It records a trace-salted question hash, answer hash and private conversation ID; existing conversation
storage remains separately protected. Normal conversation deletion removes raw messages while preserving
opaque audit/feedback IDs; audit IDs intentionally do not prevent that deletion. Answer/message writes and
their trace are committed atomically, so an audit failure does not leave a partially saved answer. The workspace displays the sanitized trace. Feedback automatically
links the appropriate immutable trace when available, alongside its source and conversation IDs.
Legacy unscoped Demo traffic is outside this institutional audit layer. Users must still avoid entering
personal health records into the demo or its evaluation data.

## Publication gate

The education review API reruns the shared deterministic rules before publishing a specific revision.
Invalid version/scope/identity/checksum/citation results block publication. Missing semantic support remains
`Review Required`: only an authenticated Reviewer/Admin can explicitly approve with a reason, for exactly
that revision. The immutable `release_reviews` record retains rule results, the manual decision and the
experiment snapshot. This is recorded authorization, not proof of clinical competence or semantic safety.
Nurse cannot publish, and stale revisions cannot reuse an approval.

`GET /api/education/drafts/{id}/release-reviews` exposes records only to staff with access to all original
sources. Source events, education revisions/events, query traces, feedback and release reviews have database
UPDATE/DELETE guards and no mutation APIs. These are basic application safeguards, not cryptographic
protection against the database owner or a privileged infrastructure attacker.

## Offline / CI release reports

```sh
python -m evaluation.medical_rules evaluation/medical_rules_cases.json /tmp/rules.json
python -m evaluation.release_gate /tmp/rules.json /tmp/gate.json
```

The negative fixture run intentionally exits 2 (Fail). CLI exit codes are 0 Pass, 2 Fail and 3 Review
Required. It replays checks from the frozen source catalog/trace, ignores fixture expected outcomes and
rejects altered checks or contradictory summaries. JSON/Markdown reports use fresh, non-overwriting paths.
The retrieval baseline exporter now includes the full experiment snapshot; `--medical-rules` adds same-corpus
rule results. CI verifies that synthetic failures block release and retains JSON/Markdown in each run's
GitHub step summary so historical runs can be compared. This regression step is not a claim that #8's
human-reviewed clinical baseline exists.

For Review Required, freeze `snapshot` into the input report before approval. A trusted operator may provide
`--approval approval.json`, containing `report_sha256` (the report's canonical digest), `reviewer`,
`role` (`reviewer`/`admin`), `decision: approve`, `reason` and timezone-aware `reviewed_at`. Changes to the
report invalidate that approval. No approval can override Fail. CLI review files are trusted operator
artifacts, not an identity provider: protect them with CI/environment permissions. Online publication uses
server-authenticated roles instead of trusting a JSON role field. Real production auto-deployment must
consume the gate exit code; this repository's workflow verifies gates but does not deploy a live service.
