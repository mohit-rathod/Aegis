---
document_id: AEGIS-KB-014
title: "Order lookup and identity verification"
company: Aegis
category: support
version: "1.0.0"
effective_date: "2026-10-16"
language: en-IN
fictional: true
---

# Order lookup and identity verification

## What is needed for an order lookup?
Ask for the Aegis order reference, such as AEG-1001. The application must associate the conversation with an authenticated customer before showing order details. An order number, email typed in chat, or spoken claim of ownership is not sufficient authorization.

## What may the assistant reveal?
The order tool checks ownership using trusted session identity. For an authorized order, report only fields returned by that tool, such as status and an estimated delivery window. An estimated date must be described as estimated. Do not reveal full addresses, payment details, or another customer's order data.

For unknown or unauthorized references, use the same neutral response: "I could not retrieve that order for this session. Please verify the reference or contact support." Do not disclose whether another customer's order exists. The assignment's seeded demo identity simulates authentication; it is not production verification. If no authenticated context exists, offer the secure support flow or a human handoff.
