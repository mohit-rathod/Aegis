# Retrieval design

Aegis retrieves from the 15 manifest-listed fictional support documents using token-bounded child passages and normalized local sentence-transformer embeddings. NumPy cosine search ranks passages; the best matching unique parent documents provide full policy context so exceptions remain attached.

ProductQuestionAgent owns this capability within the shared support system. GroundedAnswerer requests structured claims from the shared async Groq client. Citation membership is validated deterministically, the response boundary rejects unsupported transactional claims, and GroundingOutputGuard checks semantic support before delivery.

Source SHA-256 hashes, model/revision, dimensions and chunk settings are validated against the local index. Only manifest-listed document bodies are embedded. Evaluation answers, internal prompts and README files stay outside retrieval. Similarity threshold 0.25 is a development starting point, not a confidence probability. The current document bytes and indexing settings have not changed during consolidation.

The retrieval and indexing CLI commands are developer tooling. Public customer questions always enter SupportService before reaching this handler. Actual order facts require authorized tools; static policy documents cannot prove ownership, approval, initiation or ticket submission.
