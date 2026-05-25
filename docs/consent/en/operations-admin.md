# Consent Module: Use and Administration

- [To the consent section](./README.md)
- [To the general documentation section](../README.md)

## What kind of document is this

The document describes the practical operation of the consent module:
- how to connect a module to a project;
- where and what is configured in the administrative panel;
- how to link a consent document to an application form;
- How to change the flow from web confirmation to paper confirmation.

## Quick launch path

1. Connect apps and routes.
2. Perform migrations.
3. Register processing purposes and documents.
4. Publish active document revisions.
5. Bind the `purpose_code + document_code` stream to the form.
6. Check the consent status on the form and call `accept_consent` when submitting.
7. For a paper script, enable `verified_consents`, configure the policy and download the signed file.

## Connection to the project

### Applications

Minimum set:

```python
INSTALLED_APPS = [
    # ...
    "django_consent_152fz",
]
```

For paper confirmation, add:

```python
INSTALLED_APPS = [
    # ...
    "django_consent_152fz",
    "django_consent_152fz.verified_consents",
]
```

### Routes

```python
from django.urls import include, path

urlpatterns = [
    path(
        "",
        include(
            ("django_consent_152fz.urls", "django_consent_152fz"),
            namespace="django_consent_152fz",
        ),
    ),
]
```

Key routes:
- `/consent/documents/<purpose>/<document>/` - document viewing;
- `/consent/documents/<purpose>/<document>/pdf/` - printed PDF document;
- `/consent/accept/<purpose>/<document>/` - recording consent;
- `/consent/withdraw/<purpose>/<document>/` - withdrawal of consent;
- `/consent/self-service/` - subject self-service.

### Migrations

```bash
python manage.py migrate
```

## Settings `DJANGO_CONSENT_152FZ`

Basic work profile:

```python
DJANGO_CONSENT_152FZ = {
    "enable_core": True,
    "enable_access_policies": False,
    "subject_consents": {
        "open_mode": "page",
        "allow_anonymous_withdraw": True,
        "consent_input_mode": "radio",
        "checkbox_required": True,
        "decline_action": "block_submit",
        "decline_warning_enabled": True,
        "decline_warning_text": (
            "Если вы не согласны на обработку персональных данных, "
            "мы не сможем обработать заявку."
        ),
    },
}
```

Important:
- the actual activation of the paper circuit is determined by the connection
`django_consent_152fz.verified_consents` to `INSTALLED_APPS`;
- the `enable_verified_consents` key is preserved for backward compatibility,
but is not the main switch.

## Full menu map of the administrative panel

The following are the main entities that are used to support consents.

### `ConsentPurpose` (processing purposes)

What can be configured:
- target code and name;
- description;
- fieldset(`fields_config`);
- reconsent policy and subject availability.

When to change:
- when a new form business flow appears.

### `LegalDocument` (documents)

What can be configured:
- document code;
- Name;
- document type;
- activity.

When to change:
- when adding a new document under a target or a new flow.

### `DocumentRevision` (document revisions)

What can be configured:
- link to the document and `purpose_code`;
- format and content of the editorial board;
- publication (`is_active`) and version.

When to change:
- when updating the consent text.

Important:
- it is the edition of the document that becomes a legally significant point,
to which the consent record is linked.

### `ConsentAudienceRule` (audience rules)

What can be configured:
- whether consent is required for the selected audience;
- coverage (all, group, range).

When to change:
- when only a portion of users/groups need consent.

### `ConsentAccessPolicy` (access policies)

What can be configured:
- resource and action;
- reaction in the absence or outdated consent;
- link with `purpose + document`.

When to change:
- if consent must limit access to an activity/resource.

### `ConsentRecord` (consent records)

Mode:
- viewing only.

Purpose:
- checking current/obsolete/revoked status;
- audit by user, anonymous token, source.

### `ConsentEvent` (consent events)

Mode:
- viewing only.

Purpose:
- immutable event log (issue, revocation, expiration, confirmation).

### `PersonalDataManagerAssignment`

What can be configured:
- appointment of those responsible for personal data;
- rights to manage flows and verifiable consents.

Peculiarities:
- access only to superuser.

### `ConsentSelfServiceSettings`

What can be configured:
- self-care behavior;
- confirmation interface mode;
- Print PDF options;
- CSV export separator.

Peculiarities:
- single entry;
- access only to superuser.

### `ConsentModuleOperationAuditLog`

Mode:
- viewing only.

Purpose:
- log of consent module operations (actions of the admin panel and services).

## Where to view signed consents

Main operating point: section `ConsentRecord`.

How to search for signed ones:
1. Open the `ConsentRecord` list.
2. Set the filter by `Статус`:
   - `current` - currently signed;
   - `outdated` - previously signed, but deprecated.
3. If necessary, filter by target (`purpose`) and source (`source`).
4. For the user, use search by login/subject ID.
5. For an anonymous stream, use `anonymous_token` search.

What to look for in the record card:
- `purpose` and document code (`document_code`);
- `status`;
- `confirmation_method` (as confirmed);
- `source`;
- `created_at`;
- service metadata of the request in `extra_meta`.

Important:
- `ConsentRecord` in the admin panel works in view mode;
- manual editing and “retroactive correction” are not used;
- to parse the change history, go to `ConsentEvent`.

## What to do in logs and how to sort out incidents

### `ConsentRecord`: operational status analysis

When to use:
- you need to understand whether there is current agreement on the flow;
- you need to check why the form is asking for confirmation again.

Check procedure:
1. Find the last record by subject and stream `purpose + document`.
2. Check `status` and `consent_required_reason` in the application log/form context.
3. Check `confirmation_method` against the expected scenario (web or verifiable confirmation).

Available action:
- uploading selected records to CSV.

### `ConsentEvent`: operational history analysis

When to use:
- you need to understand the sequence of actions (issuance, revocation, obsolescence, confirmation);
- you need to check who confirmed or rejected the entry and when.

Check procedure:
1. Open the events of the desired consent record.
2. Sort by time (`occurred_at`).
3. Check `event_type`, `actor_type`, `actor_user`, `source`, `payload`.

Practice:
- `ConsentRecord` shows the current status;
- `ConsentEvent` shows how this state was reached.

### `ConsentModuleOperationAuditLog`: log of administrative and service operations

When to use:
- to check mass transactions;
- to analyze errors in service commands and actions in the administrative panel.

Check procedure:
1. Filter by `operation_code` or `status`.
2. Check `payload` (input parameters) and `result` (outcome).
3. For batch operations, compare the volume of processed records with the expectation.

Available action:
- uploading selected records to CSV.

## Typical tasks in the administrative panel

### It is necessary to check whether the user has signed consent on a specific form

1. Open `ConsentRecord`.
2. Find a user.
3. Filter by `purpose` and `document`.
4. Make sure the status is `current`.
5. Check `confirmation_method`.

### We need to understand why the signature does not appear on the form.

1. In `ConsentRecord` check if there is a current entry for the stream.
2. In `ConsentEvent`, check the latest events and the reason for rejection/blocking.
3. If using a paper outline, check `VerifiedConsentSubmission` and `VerifiedConsentArtifact`.
4. In `ConsentModuleOperationAuditLog`, check for service operation errors.

### We need to check the mass transfer of the flow for paper confirmation

1. Open `ConsentModuleOperationAuditLog`.
2. Find the transition operations by `operation_code` from the verified loop.
3. Check `changed_records` and the number of processed packets.
4. Additionally, check the selection of subjects in `ConsentRecord` for the desired thread.

## Additional paper outline menus

These entities are available when the application is connected
`django_consent_152fz.verified_consents`.

### `VerifiedConsentPolicy`

What can be configured:
- `verification_mode` (`web_only`, `paper_required`, `goskey_required`, `paper_or_goskey`);
- `flow_scope` (`both`, `self_service_only`, `forms_only`);
- behavior for previously issued web consents (`legacy_web_consent_policy`);
- subject notification and download modes.

What to do:
- enable/disable the requirement for paper confirmation for the flow;
- set soft or hard behavior for old web consents.

### `VerifiedConsentFormPolicy`

What can be configured:
- overriding the mode for a specific form by `form_code`;
- behavior before loading paper;
- redefining the notification channel.

What to do:
- specifically include paper confirmation only for a specific form;
- gradually expand coverage without affecting other forms of flow.

### `VerifiedConsentSubmission`

Mode:
- status board for paper confirmation requests.

Purpose:
- see what step the thread is at (`awaiting_paper_upload`,
  `paper_uploaded`, `verified`, `rejected`).

What to do:
- control the queue of applications awaiting loading or verification;
- check that the application has reached the status `verified` after processing.

### `VerifiedConsentArtifact`

Purpose:
- storage of the downloaded confirmation file and operator actions;
- confirmation or rejection of the artifact by the person responsible for the personal data.

What to do:
- open confirmation file;
- confirm or reject with comment;
- record the reason for rejection for resubmission by the subject.

## How to link a document to a form

Below is a practical script used in the demo site.

### Step 1: Capture the thread codes

For the form, define a stable link in advance:
- `purpose_code`;
- `document_code`;
- `form_code`.

Example from demo:
- `demo.contact`;
- `demo.course_signup`;
- `demo.certificate_request`.

### Step 2. Prepare the goal, document and active revision

In the administrative panel:
1. Create or update `ConsentPurpose`.
2. Create `LegalDocument`.
3. Create `DocumentRevision` for the desired `purpose_code`.
4. Publish the revision (`is_active=True`).

### Step 3. Connect the consent fields in the form

For Django form use `ConsentCaptureModeMixin`:

```python
from django import forms
from django_consent_152fz.forms import ConsentCaptureModeMixin


class ContactForm(ConsentCaptureModeMixin, forms.ModelForm):
    class Meta:
        model = ContactMessage
        fields = ("full_name", "email", "message")
```

### Step 4. Pass `verification_context` to the handler

```python
verification_context = {
    "channel": "form",
    "form_code": "demo.contact",
}
```

### Step 5: Check the stream status before sending

```python
status_info = get_consent_status(
    purpose_code=purpose_code,
    document_code=document_code,
    user=user,
    anonymous_token=anonymous_token,
    verification_context=verification_context,
)
consent_required = bool(status_info.get("requires_consent"))
```

### Step 6. If you successfully submit the form, record your consent

```python
accept_consent(
    purpose_code=purpose_code,
    document_code=document_code,
    user=user,
    anonymous_token=anonymous_token,
    confirmation_method=ConsentRecord.ConfirmationMethod.WEB_CHECKBOX,
    verification_context=verification_context,
    audit_context=build_request_audit_context(
        request,
        source="demo.contact.form",
        anonymous_token=anonymous_token,
    ),
)
```

### Step 7. In the template, provide a link to the document

There should be a clear point for the user to view the consent text:
- reference to `django_consent_152fz:document`;
- for paper script - also link to `django_consent_152fz:document_pdf`.

### Step 8: Store Anonymous Token After Replying

For anonymous scenarios, after a successful response, store the token via
`persist_anonymous_token(response, anonymous_token=...)`.

## Switching from web confirmation to paper confirmation

Below is a recommended step-by-step scenario.

### 1.Connect the paper circuit

Add to `INSTALLED_APPS`:
- `django_consent_152fz.verified_consents`.

Perform migrations.

### 2. Create a basic flow policy

In `VerifiedConsentPolicy` set:
- desired stream `purpose + document`;
- `verification_mode=paper_required` (or other mode);
- `flow_scope` for scope;
- `legacy_web_consent_policy` for legacy web consent behavior.

### 3. If necessary, set an override for the form

In `VerifiedConsentFormPolicy`:
- specify `form_code`;
- set `verification_mode_override` if the form should work differently,
than the basic flow policy.

### 4. In the form, take into account `verified_transition`

If `verified_transition.enabled=True` and status is not `verified`:
- block web signing;
- display a message about the required paper confirmation;
- Please provide a link to download the confirmation.

In the demo this is implemented for the certificate application form:
- web signing is hidden;
- a link to download the PDF and a download page for the signed file are displayed.

### 5. Organize a paper loading point

In the download handler, call `submit_verified_consent(...)` and pass:
- `purpose_code`, `document_code`;
- `paper_file`;
- `verification_context` with the same `form_code`;
- `audit_context`.

After loading, the recording will go into a pending state until it is checked by the operator.

### 6. Perform a soft translation of historical web consents

Before use, always do a preliminary run:

```bash
python manage.py transition_152fz_verified_legacy_web \
  --purpose-code certificate_issue \
  --document-code sample_certificate_issue_consent \
  --channel form \
  --form-code demo.certificate_request \
  --dry-run
```

Then batch application:

```bash
python manage.py transition_152fz_verified_legacy_web \
  --purpose-code certificate_issue \
  --document-code sample_certificate_issue_consent \
  --channel form \
  --form-code demo.certificate_request \
  --batch-size 500 \
  --apply
```

### 7. Operator processing

The person responsible for personal data checks artifacts in `VerifiedConsentArtifact`:
- confirms;
- rejects with reason.

Statuses are tracked in `VerifiedConsentSubmission`.

## Practice from demo site

Solutions that have shown consistent results:
- each application form has a constant `form_code`;
- the presentation code uses the constants `purpose_code/document_code`;
- `get_consent_status(...)` is always called before submitting the form;
- paper script blocking is processed before the form business action;
- loading paper is placed in a separate screen `verified_paper_consent`;
- after logging in and in anonymous mode, the continuity of the stream is maintained
  `anonymous_token`.

Practical smoke check checklist: `demo/notes/smoke-checklist.md`.

## Related documents

- [Settings](./configuration.md)
- [Public service API](./service-api.md)
- [Paper Confirmation Outline](./verified-flow.md)
- [Testing](./testing.md)
- [Migration](./migration.md)
