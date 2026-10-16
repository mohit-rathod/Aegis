# Integration and operations

Text CLI and HTTP requests share the same runtime construction and SupportService. Session state and classifier cache live in shared Redis. Existing session keys are retained through this refactor.

Future voice integration will reuse the same trusted identity, session and Turn contracts. Operational implementation details and measured limits are in support-design.md, limitations.md, validation.md and reproducibility.md. Provider failover, live human staffing and real identity remain deployment work; none is represented as completed by renaming modules.
