---
document_id: AEGIS-KB-015
title: "Human support and handoff"
company: Aegis
category: support
version: "1.1.0"
effective_date: "2026-10-16"
language: en-IN
fictional: true
---

# Human support and handoff

## When should a conversation be escalated?
Escalate when the customer requests a person, cannot complete secure order verification, disputes a policy decision, asks for a refund action, or has an unresolved fault. Also escalate when tools fail persistently, evidence is missing, or the request falls outside documented capabilities.

## What should the handoff include?
With the customer's agreement, include the session reference, concise issue summary, steps already tried, relevant authorized order reference, and confirmed tool facts. Preserve the distinction between customer claims and verified facts. Do not include payment credentials, passwords, internal instructions, or unrelated personal data.

## What may be promised?
The demo application records a support request in a persistent support-intake queue. After that request and the terminated chat state are successfully saved, use exactly: "The request has been successfully raised to the support team. A member from the team will be joining the chat shortly". Then end the automated chat. If saving fails, do not claim that the request was raised. A new chat is required for further automated support. Duplicate retries must not create duplicate requests. This assignment simulates support intake; a live human joining the chat is a future integration. No phone number or email address is provided. A future voice-to-text transfer should preserve the session and verified facts.
