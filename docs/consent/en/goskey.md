# Consent module: future integration with Gosklyuch

- [To the consent section](./README.md)
- [To the general documentation section](../README.md)

## Status

Integration with State Key is **not implemented** at the current stage.

Support for the `goskey_required` and `paper_or_goskey` scripts is already reserved in
verified-policy models as a direction of expansion, but working production
contour with real State Key API, organization registration and operational
process is not included in the package yet.

This is not a “hidden defect”, but a deliberately delayed part of the roadmap.

## Why is this delayed?

The authors of the project at the current stage:

- there is no own company that needs the production circuit of the State Key;
- there is no working combat scenario with legal and operational support;
- there is no way to independently register an organization and confirm
the entire external integration process in practice.

Therefore, the package does not yet pretend that the integration is ready.

## What is required for real integration

For full integration with Gosklyuch, only code in Django is not enough.

Typically required:

- legal entity or other acceptable organizational structure;
- real business need for the signing scenario;
- completing organizational registration and access approval;
- understanding the requirements from the State Key service;
- access to the latest API, its restrictions and operational rules;
- test and then workflow for signature and lifecycle verification
confirmation.

That is, the task is not only to “call the external API”, but to
to go through the entire implementation journey as an organization.

## What else needs to be explored

At least the following blocks remain open until implementation:

- current process of connecting an organization;
- requirements for the contractual and registration party;
- API availability and terms of use;
- the lifecycle of creating, waiting for, and completing a signing operation;
- callback/webhook or equivalent state exchange format;
- storage requirements for identifiers, artifacts and logs;
- handling errors, cancellations, expirations, and resubmissions;
- boundaries of responsibility between the verified-flow package and the external service.

## What is already in the package as a starting point?

The package already contains a technical background that can be used as a base
for future integration:

- `verified_consents` as a separate extensible loop;
- `verification_mode`, including `goskey_required` and `paper_or_goskey`;
- `VerifiedConsentPolicy` and `VerifiedConsentFormPolicy`;
- verified-flow service and audit framework;
- separation between basic consent-domain and method-specific confirmation.

This means that integration can be added as an extension on top of an existing one.
architecture, and not as a rewrite of the entire consents module.

## What doesn't exist yet

At the current stage **not implemented**:

- real Gosklyuch API client;
- signing operation initiation flow;
- return the signing result;
- storage and verification of artifacts of the State Key;
- operator interface for the working script of the State Key;
- confirmed compatibility with the requirements of external services;
- documentation "how to connect Gosklyuch in 15 minutes."

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

- description of the actual process of connecting an organization;
- documented API restrictions and requirements;
- test script with confirmed access;
- integration client and state machine project;
- examples of secure logging and storage of artifacts;
- checking for compatibility with existing verified-flow.

## Practical takeaway for current users

If you need a working script right now, focus on:

- `web_only`;
- `paper_required`;
- `paper_or_goskey` only as a future extension mode, not as a ready-made one
supply;
- cameraman's paper script as the actual path realized.

If the project really has a need for the State Key, it is better to immediately
lay down a separate stage of research, integration and verification with the participation
organization that will use this circuit in real work.

## Related documents

- [Experimental Confirmed Consent Contour](./verified-flow.md)
- [Use and Administration](./operations-admin.md)
- [Settings and policy contract](./configuration.md)
