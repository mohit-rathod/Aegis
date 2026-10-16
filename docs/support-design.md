# Support design and implementation

## Shared pipeline

Text and future transcribed voice enter SupportService. The service validates session ownership, serializes each session using a Redis lease, checks idempotent retries, rejects terminal sessions, applies deterministic input rules, runs Groq semantic input checks, consults the classifier cache, validates the route, and dispatches the exact approved immutable turn/context. All handler results go through ResponseService before commit and delivery.

ApprovalAuthority signs a fingerprint of the exact turn and session snapshot with a process-local key and expiration. Dispatch and tool execution verify it. Approval is never accepted from HTTP input or serialized client state. This is a control-flow invariant within a trusted Python application, not a sandbox against arbitrary code execution and not proof that semantic injection detection has perfect recall.

Malformed or unavailable required checks fail closed. A cached classification cannot authorize input or tools. Saved identical-turn retries replay the already checked response; a changed body using that turn ID is rejected. No new unchecked message is processed during replay.

## Router

Groq returns exactly one of product_question, order_status, escalate_to_human, plus clarification flag and a bounded reason. Unknown schema values fail closed. General return/refund policies use product_question. Actual order status, return eligibility, and recorded refund status use order_status. A request to execute a refund, unsupported business action, dispute or person request uses escalation. A normal refund request is allowed input, not intrinsically malicious. Unrelated mixed questions clarify first. The current implementation handles one agent per turn; it does not chain unrestricted agents.

Relevant router context consists only of the last verified order reference and pending intent. Customer text cannot update trusted identity or verified order state. The last order reference changes only after a successful authorized tool-backed answer.

## RAG

The original document-aware child-to-parent embedding retrieval remains. The async product handler performs bounded off-loop inference and sends retrieved documents to Groq for structured claims. Citation membership is checked, a conservative transactional-claim filter rejects static-KB assertions of live refund/ticket state, and the semantic output verifier checks remaining claims. Only approved claims are rendered. Similarity cutoff remains an uncalibrated development setting, not a confidence score.

## Native tool calling

Groq structured function calls were chosen over text-parsed ReAct because schemas and explicit allowlists make execution easier to validate. The application provides get_order_status and check_return_eligibility only. Tools take an order reference, not a customer ID or execution date. The executor injects trusted session identity and an application clock, checks ownership every time, validates arguments, and records application-owned evidence. Cross-customer and unknown-order responses are identical. At most two tool rounds are allowed, one call per round, followed by a final response step.

The model's final tool-path prose is discarded. ResponseService renders exact verified fields and controlled policy wording. An application-owned result vault rejects invented or modified evidence. Vault entries are request-scoped and cleaned when the owning turn ends. Read-only tool results may be reused within the same turn, never across customers through the classifier cache.

## Refund reconciliation

Eligibility is not return authorization, refund approval, or initiation. The customer-facing approved state is approved_and_initiated with initiation timestamp and original_payment_source destination. Only that tool-confirmed state triggers: The refund is initiated and will be refunded to the original payment source in the next 3-5 working days

Raw approval without initiation is inconsistent and fails closed. The assistant cannot execute a refund or infer an amount from purchase value. The 3–5 working-day wording replaces the earlier KB policy; no exact calendar credit date is calculated. Demo data includes both valid and deliberately inconsistent states.

## Escalation

The handler prepares a bounded customer-statement summary and separately labeled verified order reference. ResponseService prepares the controlled success message. Redis commits session termination, the replay response, and the support-intake record in one atomic MSET inside a lease-checked Lua script. Data values are written by one command, avoiding partial business records if a later independent queue write fails. The support inbox is the durable set of request keys, not a separate stream whose publication could fail after a success reply was saved. The admin endpoint discovers records through bounded scan iteration. This simple inbox has no chronological ordering, human assignment, acknowledgement, or live agent integration yet.

The requested success message is delivered only after persistence succeeds. Retrying the same turn replays it without duplicating intake. Subsequent messages go to the human handoff instead of AI routing. Claim enters human_active; extractive admin resolution resumes active. Customer termination rejects future messages. In-flight escalation is protected by the session lease; no separate durable escalation_pending state is needed for this atomic local demo transition.

## Cache

Redis TTL cache stores validated routing decisions only. Keys hash minimally normalized message, relevant context, model, router prompt hash and registry version. There is no semantic-answer or authorization cache. A capped access-ordered index bounds keys. The semantic input gate still runs before every new lookup. Distributed fill locks coalesce identical misses. Metrics separate hits, misses, coalesced requests, Groq calls and failures. Hit rate is hits/(hits+misses); coalesced initial misses are not retroactively relabeled hits. Provider quota avoided can be reported separately.

## Scaling to 10k sessions

The ASGI application supports multiple workers sharing Redis sessions, cache, per-session leases, idempotent responses and support intake. Each worker reuses one async HTTP client and embedding model/index. Active turns, provider requests, embedding submissions and connection pools are bounded; overload returns busy rather than accumulating an unlimited task queue. An overall turn deadline bounds sequential model work. Cancelled inference does not release its bounded slot until its underlying thread actually finishes; stale results cannot execute new tools or persist terminal actions.

10k connected sessions is not 10k simultaneous inference requests. The included capacity runner creates 10,000 session records and drives controlled active turns against real Redis with scripted providers. It is not an HTTP/network-concurrency, embedding, Groq, or voice capacity certification. Validate real arrival rates, provider quotas, token throughput, hardware, connection limits and memory before claiming production throughput. Per-worker limits do not enforce a global provider quota across arbitrarily many workers; cap deployment worker count to your account budget and add a distributed quota controller for larger deployments.

The compose uses standalone Redis, AOF, and noeviction. The multi-key Lua scripts are not Redis Cluster compatible. A production HA deployment should use a protected primary/replica or managed compatible service, an operational backup policy, TLS and real identity. Storing cache and business state on one local Redis is a timeboxed assignment choice; separate them for production resource isolation. No eviction means storage saturation returns an error and fails closed, rather than losing session ownership or terminal state.

## Fourth agent later

Registry version, classifier definitions, handler map and tool allowlist are separate. A future billing_dispute handler requires schema/registry expansion, its own tools/evidence contract, cache-version invalidation and regression coverage. The shared input/dispatch/output checks remain mandatory. The fourth intent is not implemented now.

## Evaluation

Datasets contain 45 labeled routing messages, 9 clarification cases, 24 input-safety cases, 24 output-safety cases, 12 ownership checks and the existing 20 grounding seeds. Cache evaluation runs separate 30-request unique and repeated workloads. These are development examples; add fresh held-out paraphrases before claiming generalization.

The live runner reports routing accuracy, macro-F1, confusion matrix, clarification rate, input attack recall/benign false-positive rate, output unsupported-claim rejection/valid-claim rejection, tool authorization accuracy and cache counters. Operational provider errors fail closed but are excluded from semantic recall denominators and counted separately. Structural tests assert no dispatch after blocked/failed input, exact-context approval, no unauthorized tools, no forged evidence, exact refund wording, escalation persistence-before-success, termination, replay/conflict behavior, output rejection and shared Redis state visibility.

Actual authoring results and honest limitations appear in docs/validation.md. Do not interpret deterministic fake-model tests as model accuracy or guardrail recall.
