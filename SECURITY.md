# Security Policy

[Русская версия](./SECURITY.ru.md)

This repository ships two independently versioned packages: `django-consent-152fz`
(personal-data consent lifecycle) and `django-cookies-152fz` (cookie banner and
runtime). Both handle personal data in a 152-FZ context, including an immutable
audit trail. Please treat security issues accordingly.

## Supported versions

The two packages are versioned independently; always upgrade to the latest release
of each. Security fixes are provided for the latest released version of each package
and the `main` branch only.

| Package | Version | Supported |
| --- | --- | --- |
| `django-consent-152fz` | latest released version | ✅ |
| `django-cookies-152fz` | latest released version | ✅ |
| any | older or pre-release builds | ❌ |

> Upgrade promptly when a security release is published.

## Reporting a vulnerability

Please do not open a public GitHub issue, pull request, or discussion for security
problems. Public disclosure before a fix puts data subjects at risk.

Report privately through GitHub:

1. Go to the repository
   [github.com/kroxiksut/django-consent-152fz](https://github.com/kroxiksut/django-consent-152fz).
2. Open the **Security** tab -> **Report a vulnerability**.

If private reporting is unavailable to you, contact the maintainer privately via
GitHub instead of filing a public issue.

### What to include

- affected package and version (`django-consent-152fz` and/or `django-cookies-152fz`);
- the affected module or path and, if known, the relevant code location;
- a minimal reproduction or proof of concept;
- the impact you observed (data exposure, audit-log integrity, privilege escalation,
  and similar);
- any suggested remediation.

Do not include real personal data in your report; use synthetic data.

### What to expect

- acknowledgement of the report as soon as the maintainer can triage it;
- an assessment of severity and affected versions;
- a coordinated fix and release, followed by public disclosure through a GitHub
  Security Advisory once a fix is available;
- credit for the reporter on request.

This is an open-source project maintained on a best-effort basis; response times are
not contractually guaranteed.

## Security model and trust boundaries

Several behaviors are secure only when deployed as documented. Misconfiguration
here is the most likely source of real-world issues, so they are listed explicitly:

- HTML revision authoring is trusted-only. Legal-document and banner revision bodies
  authored as HTML are rendered without sanitization. Restrict authoring of HTML
  revisions to trusted staff roles.
- Client IP and `X-Forwarded-For`. The audit log records the client IP. Trust
  `X-Forwarded-For` only behind a correctly configured trusted proxy; otherwise the
  IP recorded in the immutable audit can be spoofed via the header.
- Anonymous consent token is a bearer secret. It is transported as a `Secure`,
  `HttpOnly`, `SameSite=Lax` cookie and is never accepted from query strings. Serve
  the site over HTTPS and do not log the token.
- Immutable audit log. Consent and cookie events are append-only and protected
  against deletion, including bulk-delete and retention flows, by design. Do not
  bypass the immutable managers.
- Admin CSV exports are protected against CSV formula injection; subject-controlled
  fields are neutralized on export.
- Cookie script execution uses a positive allow-list for script sources rather than
  a blocklist.

For the full set of audited controls and invariants, see the module documentation:
consent (`docs/consent/en/`) and cookies (`docs/cookies/en/`), in particular the
`invariants`, `configuration`, and `operations-admin` pages.

## Scope

In scope: vulnerabilities in the package source under `src/` that affect
confidentiality, integrity, or availability of consent and cookie data, the audit
log, or the admin and API surface.

Out of scope: issues that require an already-compromised trusted role, documented
trust-boundary behavior such as trusted HTML authoring, vulnerabilities in
third-party dependencies, and findings that apply only to deployments configured
against the documented guidance.
