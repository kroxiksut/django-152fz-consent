# Consent module: future integration with Gosklyuch

- [To the consent section](./README.md)
- [To the general documentation section](../README.md)

## Status

Integration with Gosklyuch is **not implemented** at the current stage.

Support for the `goskey_required` and `paper_or_goskey` scenarios is already reserved in
the verified-policy models as a direction for expansion, but a working production
flow with a real Gosklyuch API, organization registration and operational
process is not yet included in the package.

This is not a "hidden defect", but a deliberately deferred part of the roadmap.

## Why is this deferred?

At the current stage, the project authors have:

- no company of their own that needs a production Gosklyuch flow;
- no live working scenario with legal and operational support;
- no way to independently register an organization and validate
the entire external integration process in practice.

Therefore, the package does not yet pretend that the integration is ready.

## What is required for real integration

Code in Django alone is not enough for full integration with Gosklyuch.

Typically required:

- a legal entity or other acceptable organizational structure;
- a real business need for the signing scenario;
- completing organizational registration and access approval;
- understanding the requirements of the Gosklyuch service;
- access to the current API, its restrictions and operational rules;
- a test and then a production workflow for signing and lifecycle verification of
confirmations.

In other words, the task is not just to "call the external API", but to
go through the entire implementation journey as an organization.

## What else needs to be explored

At least the following blocks remain open until implementation:

- the current process of connecting an organization;
- requirements for the contractual and registration side;
- API availability and terms of use;
- the lifecycle of creating, waiting for, and completing a signing operation;
- the callback/webhook or equivalent state-exchange format;
- storage requirements for identifiers, artifacts and logs;
- handling errors, cancellations, expirations, and resubmissions;
- boundaries of responsibility between the verified-flow package and the external service.

## What is already in the package as a starting point?

The package already contains a technical foundation that can be used as a base
for future integration:

- `verified_consents` as a separate extensible flow;
- `verification_mode`, including `goskey_required` and `paper_or_goskey`;
- `VerifiedConsentPolicy` and `VerifiedConsentFormPolicy`;
- the verified-flow service and audit framework;
- separation between the basic consent domain and method-specific confirmation.

This means integration can be added as an extension on top of the existing
architecture, rather than as a rewrite of the entire consents module.

## What doesn't exist yet

At the current stage the following is **not implemented**:

- a real Gosklyuch API client;
- the signing-operation initiation flow;
- returning the signing result;
- storage and verification of Gosklyuch artifacts;
- an operator interface for the Gosklyuch working scenario;
- confirmed compatibility with external service requirements;
- documentation on "how to connect Gosklyuch in 15 minutes".

## Our position on development

If you have:

- company;
- real need for integration;
- the ability to register and gain access;
- willingness to test not only the code, but also the external process,

This direction is quite open for joint improvement.

We are ready:

- accept a meaningful pull request;
- help with architectural integration into the current verified-flow;
- help with review of data model, statuses, logging and contracts;
- participate in the refinement and testing of integration within the framework of real
implementation.

## Which contribution would be particularly helpful?

The most valuable contribution to moving in this direction:

- a description of the actual process of connecting an organization;
- documented API restrictions and requirements;
- a test scenario with confirmed access;
- a design for the integration client and state machine;
- examples of secure logging and storage of artifacts;
- a compatibility check against the existing verified-flow.

## Practical takeaway for current users

If you need a working scenario right now, focus on:

- `web_only`;
- `paper_required`;
- `paper_or_goskey` only as a future extension mode, not as a ready-made
offering;
- the operator's paper flow as the path that is actually implemented.

If the project genuinely needs Gosklyuch, it is better to plan a separate
stage of research, integration and verification up front, with the participation of an
organization that will use this flow in real operation.

## Related documents

- [Experimental verified consent flow](./verified-flow.md)
- [Use and administration](./operations-admin.md)
- [Settings and policy contract](./configuration.md)
