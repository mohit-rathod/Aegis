---
document_id: AEGIS-KB-015
title: "Human support and handoff"
company: Aegis
category: support
version: "1.2.0"
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
The application records a support request and moves the same session into a waiting-for-human state. Only after persistence succeeds, use exactly: "The request has been successfully raised to the support team. A member from the team will be joining the chat shortly". An authenticated support operator can then join the admin chat. Customer text or transcribed speech reaches that operator; operator replies appear in the customer transcript and are spoken when voice is enabled. Availability depends on an operator actually signing in; do not claim a person has joined before that happens.

## How does human support end?
The operator can end the human handoff. The system summarizes recorded human guidance and any optional final note, returns that summary to the customer, and resumes the AI assistant in the same session. Human statements are conversation context, not verified order facts or authorization to execute refunds. The customer can end the entire conversation at any time; this closes the session and prevents further human or AI messages. Reconnection may resume an open session, but a closed session must not be silently reopened. Duplicate retries must not create duplicate support requests or replies.
