# Integration and operations

Text CLI and HTTP requests share the same runtime construction and SupportService. Session state and classifier cache live in shared Redis. Existing session keys are retained through this refactor.

Browser voice reuses the same trusted identity, session and Turn contracts; see voice-design.md and voice-demo.md. Operational implementation details and measured limits are in support-design.md, limitations.md, validation.md and the root README.md. Provider failover, live human staffing and real identity remain deployment work; none is represented as completed by renaming modules.

The current file map is [ARCHITECTURE.md](../ARCHITECTURE.md); fresh-checkout setup is in [README.md](../README.md).
