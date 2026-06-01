# Security Policy

[Русская версия](./SECURITY.ru.md)

This repository ships two independently versioned packages — `django-consent-152fz`
(personal-data consent lifecycle) and `django-cookies-152fz` (cookie banner and
runtime). Both handle **personal data** in a 152-FZ context, including an immutable
audit trail. Please treat security issues accordingly.

## Supported Versions

The two packages are versioned independently; always upgrade to the latest release
of each. Security fixes are provided for the latest released version and the `main`
branch only.

| Package | Version | Supported |
| --- | --- | --- |
| `django-consent-152fz` | latest `0.1.x` | ✅ |
| `django-cookies-152fz` | latest `0.1.x` | ✅ |
| any | older / pre-release builds | ❌ |

> The project is currently in **alpha** (`0.1.0`). APIs and contracts may change;
> upgrade promptly when a security release is published.

## Reporting a Vulnerability

**Please do not open a public GitHub issue, pull request, or discussion for security
problems** — public disclosure before a fix puts data subjects at risk.

Report privately through GitHub:

1. Go to the repository
   [github.com/kroxiksut/django-152fz-consent](https://github.com/kroxiksut/django-152fz-consent).
2. Open the **Security** tab → **Report a vulnerability** (GitHub private vulnerability reporting).

If private reporting is unavailable to you, contact the maintainer privately via
GitHub instead of filing a public issue.

### What to include

- affected package and version (`django-consent-152fz` and/or `django-cookies-152fz`);
- the affected module/path and, if known, the relevant code location;
- a minimal reproduction or proof of concept;
- the impact you observed (data exposure, integrity of the audit log, privilege
  escalation, etc.);
- any suggested remediation.

Do **not** include real personal data (PII) in your report — use synthetic data.

### What to expect

- acknowledgement of the report as soon as the maintainer can triage it;
- an assessment of severity and affected versions;
- a coordinated fix and release, followed by public disclosure (a GitHub Security
  Advisory) once a fix is available;
- credit for the reporter on request.

This is an open-source project maintained on a best-effort basis; response times are
not contractually guaranteed.

## Security model and trust boundaries

Several behaviors are secure **only when deployed as documented**. Misconfiguration
here is the most likely source of real-world issues, so they are listed explicitly:

- **HTML revision authoring is trusted-only.** Legal-document and banner revision
  bodies authored as HTML are rendered without sanitization. Restrict authoring of
  HTML revisions to trusted staff roles. See the consent authoring and configuration
  docs.
- **Client IP / `X-Forwarded-For`.** The audit log records the client IP. Trust
  `X-Forwarded-For` only behind a correctly configured trusted proxy; otherwise the
  IP recorded in the immutable audit can be spoofed via the header. Configure the
  trusted-proxy settings accordingly.
- **Anonymous consent token is a bearer secret.** It is transported as a `Secure`,
  `HttpOnly`, `SameSite=Lax` cookie and is never accepted from query strings. Serve
  the site over HTTPS and do not log the token.
- **Immutable audit log.** Consent/cookie events are append-only and protected
  against deletion (including bulk-delete and retention) by design. Do not bypass the
  immutable managers; retention of immutable models requires a real archive sink.
- **Admin CSV exports** are protected against CSV formula injection; subject-controlled
  fields are neutralized on export.
- **Cookie script execution** uses a positive allow-list for script sources rather
  than a blocklist.

For the full set of audited controls and invariants, see the module documentation:
consent (`docs/consent/en/`) and cookies (`docs/cookies/en/`), in particular the
`invariants`, `configuration`, and `operations-admin` pages.

## Scope

In scope: vulnerabilities in the package source under `src/` that affect
confidentiality, integrity, or availability of consent/cookie data, the audit log, or
the admin/API surface.

Out of scope: issues that require an already-compromised trusted role (e.g. malicious
HTML authored by a trusted staff account — this is a documented trust boundary, not a
vulnerability), vulnerabilities in third-party dependencies (report those upstream),
and findings that only apply to deployments configured against the documented
guidance.
