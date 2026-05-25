# Consent Forms Guide (AI)

## Goal

Bind a concrete consent stream to a concrete project form.

## Stable identifiers

For each form, define:

- `purpose_code`
- `document_code`
- `form_code` (recommended for verified policies)

## Runtime sequence

1. Build `verification_context`:
   `{"channel": "form", "form_code": "<stable_form_code>"}`
2. Call `get_consent_status(...)` before form business logic.
3. If consent is required:
   block submit until explicit user confirmation.
4. After successful confirm:
   call `accept_consent(...)` with `audit_context`.
5. For anonymous subject flow:
   persist `anonymous_token` in response.

## Rendering contract

- Always provide a link to document view route.
- For printable flows, provide a PDF route link.
- Keep consent UI independent from domain form fields.

