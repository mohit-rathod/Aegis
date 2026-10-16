# Aegis knowledge-base integration

All company details, products, specifications, and policies in this pack are invented for the technical assignment. They are not statements about any real company named Aegis. This is a dummy support reference set, not legal, medical, or certified product documentation.

## Package contents
- `data/knowledge_base/`: the 15 retrieval documents and their manifest.
- `evaluation/datasets/aegis_grounding_seed.jsonl`: 20 manually authored development questions and expected facts. This is a seed set, not a measured evaluation report or a hidden test set.
- This README: integration instructions, excluded content, and limitations.

## Placement in your existing project
Copy the package's `data/knowledge_base/` contents into your project's matching folder. Copy the evaluation seed to `evaluation/datasets/` alongside your other evaluation files. Do not replace your entire data or evaluation directory. If your scaffold has an empty knowledge-base manifest, replace it with this manifest; if it already contains real documents, merge deliberately and retain unique IDs. No source code, secret, fixture order, or audio recording is included.

## Retrieval ingestion
1. Read `data/knowledge_base/manifest.json` and load only each listed Markdown path. Do not recursively ingest README files, evaluation answers, source code, prompts, or internal design notes.
2. Parse YAML front matter as metadata and remove it from the text passed to embeddings. Keep the title and question headings in each passage.
3. Each document is short enough to start as one passage. If splitting later, preserve document ID, heading, relative source path, version, and a stable chunk ID such as `AEGIS-KB-012:001`.
4. Generate embeddings with your chosen local embedding model. Save its identifier, embedding dimension, document hashes, and index build time with the generated index under `var/indexes/`.
5. Embed the query with the same model and compare normalized vectors. Start with top-k 3 and tune any similarity threshold on development examples. Similarity is not an answer-correctness probability.
6. Supply retrieved passages as reference data, not executable instructions. Require valid document citations, supported claims, and an explicit abstention when information is missing.
7. Validate that cited IDs were actually retrieved. Valid citation IDs alone do not prove a claim is supported; run the output claim check as well.

## Knowledge versus live state
The KB explains rules; it does not confirm a specific order's status, ownership, delivery timestamp, eligibility, refund amount, or payment initiation. Those require authorized tools. The application obtains customer identity from trusted session state, not from chat text. Both text and transcribed voice must use the same input-guarded support pipeline.

Return eligibility, return authorization, refund approval, and payment initiation are separate states. This pack defines that distinction explicitly. An eligibility-only tool cannot confirm a refund amount or credit date. The same applies to delivery estimates versus guarantees.

## Suggested seed tests
Use the supplied development questions for retrieval inspection and grounded-answer checks. For `tool_required`, test that the engine requests authorized live facts rather than answering from the KB. For `abstain`, test that it states the missing information without fabricating a value. A valid answer may cite a subset of the listed supporting IDs; there is no requirement to cite every listed source. Create fresh held-out paraphrases and red-team examples separately; do not claim these seed questions are an independent benchmark.

Useful additional attacks: claim to be a manager authorizing a refund; paste a fake tool result; request another customer's order; ask for a guaranteed arrival date; say the Pure Mini is already connected to Wi-Fi and demand reset instructions. Keep attack prompts and expected answers outside the retrieval corpus.

## Demo and limitations
The fictional Aegis Home app has no live download URL. No real store, phone number, email address, support SLA, ticket integration, service-status feed, price list, or audio clips are provided. Do not represent a generated handoff summary as a submitted ticket. Record real human audio separately for the assignment's voice tests.

Date-dependent tools need a trusted clock and explicit business-calendar behavior. This KB supplies calendar-day return rules but no holiday calendar. Do not derive guaranteed delivery or bank-credit dates from generic business-day ranges.

## Document inventory
- `AEGIS-KB-001` — `products/product-overview.md`: Aegis Pure product overview.
- `AEGIS-KB-002` — `products/filter-compatibility.md`: Filter compatibility and accessories.
- `AEGIS-KB-003` — `products/filter-care.md`: Filter cleaning and replacement.
- `AEGIS-KB-004` — `setup/first-use.md`: First-use installation.
- `AEGIS-KB-005` — `setup/wifi-pairing.md`: Pure Plus Wi-Fi pairing.
- `AEGIS-KB-006` — `setup/indicator-guide.md`: Indicator lights and filter reset.
- `AEGIS-KB-007` — `troubleshooting/low-airflow.md`: Troubleshooting weak airflow.
- `AEGIS-KB-008` — `troubleshooting/noise-and-vibration.md`: Troubleshooting noise and vibration.
- `AEGIS-KB-009` — `troubleshooting/device-offline.md`: Troubleshooting an offline Pure Plus.
- `AEGIS-KB-010` — `policies/shipping.md`: Shipping and delivery policy.
- `AEGIS-KB-011` — `policies/returns.md`: Return eligibility policy.
- `AEGIS-KB-012` — `policies/refunds.md`: Refund decisions and payment timing.
- `AEGIS-KB-013` — `policies/warranty.md`: Limited warranty policy.
- `AEGIS-KB-014` — `support/order-status-and-verification.md`: Order lookup and identity verification.
- `AEGIS-KB-015` — `support/human-escalation.md`: Human support and handoff.
