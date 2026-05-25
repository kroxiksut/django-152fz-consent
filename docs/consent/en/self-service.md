# Consent Module: Subject Self-Service Scenarios

- [To the consent section](./README.md)
- [To the general documentation section](../README.md)

## Alpha area

Self-service in the current area covers:
- view current subject consents;
- withdrawal of consent for a specific stream `purpose + document`.

## What is not included in the scope

- A full-fledged personal account with arbitrary legal work scenarios.
- Complete “right to be forgotten” process with external workflow and SLA.

## Behavior Settings

`DJANGO_CONSENT_152FZ["subject_consents"]`:
- `open_mode`: `page` | `new_window` | `modal`;
- `consent_input_mode`: `checkbox` | `radio`;
- `checkbox_required`: confirmation required;
- `decline_action`: `block_submit` | `allow_submit`;
- `allow_anonymous_withdraw`: Anonymous review policy.

## Route

- `django_consent_152fz:subject_consents` (`/consent/self-service/`).

## Localization

- The self-service interface uses the standard Django localization contract (`.po/.mo`).
- Changes to custom strings are accompanied by translation updates.
