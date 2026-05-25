# Cookie module: event and interception contract

- [Go to cookies section](./README.md)
- [To the general documentation section](../README.md)

## DOM Event Contract

The client layer `cookie_banner.js` publishes events:
- `dz152fz:cookie-runtime:applied`;
- `dz152fz:cookie-runtime:cleanup-applied`;
- `dz152fz:cookie-banner:opened`;
- `dz152fz:cookie-banner:closed`;
- `dz152fz:cookie-banner:custom-opened`;
- `dz152fz:cookie-banner:action-submitted`.

Total payload:
- `contract_version`, `contract_namespace`, `event_key`, `event_name`, `timestamp`;
- specific event fields (`allowed_categories`, `removed_categories`, `action`, `selected_optional_categories` and others).

## Server interceptions for integrations

The cookie service layer publishes an extension point:
- `set_cookie_runtime_event_hook(...)` — callback registration;
- `trigger_cookie_runtime_event(payload)` - call the callback from the execution thread.

Responsibility for specific project adapters remains with the project.

## Request audit-context: country, browser and OS

`build_request_audit_context(...)` in the cookie package adds best-effort enrichment to `extra_meta.client`:
- `country_code` (ISO alpha-2);
- `country_source` (`header:<name>` or `locale`);
- `browser_name`, `browser_version_major`;
- `os_family`, `os_version_major`.

The data is optional and is filled in only when it can be determined correctly.
