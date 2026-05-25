# Consent module: creating and filling consents

- [To the consent section](./README.md)
- [To the general documentation section](../README.md)

## Purpose

This document describes a practical way to create consents:

- how to start a stream `цель + документ`;
- how to choose a text format;
- how to work with starter templates;
- how to edit texts in the admin panel;
- how to connect a visual editor if necessary.

## What does the flow of consent consist of?

In the consents module, the workflow is assembled from several entities:

1. `ConsentPurpose` - purpose of processing.
2. `LegalDocument` - the document itself.
3. `DocumentRevision` - specific edition of the document text.
4. `ConsentRecord` - fact of issued consent.
5. `ConsentEvent` - log of changes to this fact.

Practically this means:

- first you describe the goal;
- then create a document;
- then publish an edit of the text;
- Only then can the application form rely on this flow.

## Minimum procedure for creating consent

The recommended order is:

1. Create `ConsentPurpose`.
2. Create `LegalDocument`.
3. Create `DocumentRevision`.
4. Publish an active editorial team.
5. Bind `purpose_code + document_code` to a form or script.
6. Check `get_consent_status(...)` before the form business action.
7. Call `accept_consent(...)` only on successful and explicit confirmation.

## How to fill out the purpose of processing

For `ConsentPurpose` it is usually sufficient:

- stable `code`;
- understandable `title`;
- short `description`;
- list of fields in `fields_config`;
- revocation policies;
- re-consent regime;
- Subject Availability Policy.

Practical recommendations:

- `code` should be stable and machine-friendly;
- `title` must be readable by the administrator;
- `description` is best written as a business explanation rather than a legal text;
- the list of fields should reflect the real data that is processed in this
flow, and not an abstract “reserve for the future.”

## How to fill out a document

`LegalDocument` is a container for revisions.

Typically it asks:

- `code`;
- `title`;
- `document_type`;
- description and activity.

Practice:

- do not mix different business scenarios in one document;
- if the scripts have different texts or different legal grounds, create
separate documents;
- use stable `document_code` so that application code does not depend on
title of the document in the interface.

## How to fill out the text edition

The legally significant point is precisely `DocumentRevision`.

In the editorial you ask:

- link to the document;
- `purpose_code`;
- `version`;
- `format`;
- text or file;
- editorial publication.

What is important in practice:

- it is the edition, and not `LegalDocument` itself, that is used as the basis for
consent bindings;
- publication of a new edition affects re-consent and obsolescence status;
- old editions should not be rewritten retroactively.

## Which text format to choose

Currently supported:

- `plain_text`;
- `markdown`;
- `html`;
- file editions, including PDF and office formats.

Recommended choice:

- `markdown` - the main working option for most projects;
- `plain_text` - if you need very simple and predictable text without markup;
- `html` - if you need more complex control over the structure and design;
- file - if the text comes as an approved external document and must
supplied without reassembly in the text field.

Rule of thumb:

- for new boxed and custom templates it is usually better to start with
  `markdown`;
- `html` should be used where control over
structure, and not just because “it’s more common”;
- PDF and other file formats are suitable for printed, approved or
externally consistent editions.

## What to write in the consent text

The module stores and displays text, but does not write a legally correct document
for you.

When filling out the revision, you usually need to explicitly reflect:

- who is the operator;
- what specific purpose of processing is covered;
- what categories or data fields are processed;
- how the subject confirms consent;
- how the subject can withdraw consent;
- where is the linked document if the consent is part of a larger one
package of documents.

Not recommended:

- use the same general text for all forms without checking the meaning;
- list data that is not actually collected in this stream;
- copy text from another project without adapting it to your processing model.

## Starter templates and boxed texts

The package already knows how to load starting document templates.

Their purpose:

- give a working starting point;
- reduce the first connection time;
- show the recommended flow and revision structure.

What's important:

- boxed editions are considered samples;
- they need to be tested and adapted;
- for production implementations it is better to make a custom copy and modify it already
her;
- you should not perceive the starting text as automatically ready-made legal
document.

## How to work in the admin area without confusion

A practically safe way is this:

1. Download starter templates if needed.
2. Find a boxed edition.
3. Create a custom copy from it.
4. Edit custom copy.
5. Publish the custom edition as active.

This is better than changing the boxed edition directly because:

- the original sample is preserved;
- you can see where the starting template is and where the working version of the project is;
- It's easier to maintain a history of changes.

## How to edit text in the admin panel

By default, the admin panel of the consent module works according to the principle
`markdown-first`/`textarea-first`:

- the core does not require a mandatory external visual editor;
- the text edition is already suitable for normal workflow;
- Plain text, markdown or HTML can be used if necessary.

This is a conscious decision:

- basic installation remains easier;
- the document flow does not carry unnecessary dependencies;
- the integrator himself decides whether a visual editor is needed.

## Is it possible to connect WYSIWYG

Yes. The code already provides for connecting an external widget for editing
`DocumentRevision.content_text`.

If you already have an editor installed in your project, you can use
it by passing the widget class path through the settings.

If the project does not yet have an editor, you can install it separately and
connect in the same way.

At the current stage, the module does not impose a specific library and does not provide
native WYSIWYG as a required dependency.

## Settings for the administrative document editor

The settings live in `DJANGO_CONSENT_152FZ["document_templates"]`.

In particular, they support:

- `default_text_format`;
- `admin_editor_mode`;
- `admin_wysiwyg_widget`;
- `admin_wysiwyg_widget_attrs`;
- `html_to_pdf_hook`.

Example:

```python
DJANGO_CONSENT_152FZ = {
    "document_templates": {
        "default_text_format": "markdown",
        "admin_editor_mode": "wysiwyg",
        "admin_wysiwyg_widget": "myproject.widgets.ProjectRichTextWidget",
        "admin_wysiwyg_widget_attrs": {
            "rows": "24",
            "data-editor-profile": "legal",
        },
        "html_to_pdf_hook": "",
    },
}
```

What does it mean:

- `default_text_format` sets the default text format for new revisions;
- `admin_editor_mode` switches the expected operating mode of the admin panel;
- `admin_wysiwyg_widget` specifies the imported Django Forms widget class;
- `admin_wysiwyg_widget_attrs` allow you to pass parameters to the widget;
- `html_to_pdf_hook` reserves the path for project-based HTML to PDF conversion.

## How to safely use an external editor

Recommended approach:

1. First check the plain text or markdown stream.
2. Connect WYSIWYG only if the team really needs it
visual editing.
3. Use an existing project editor if you have one.
4. Before publishing, check the final edit for actual HTML output,
structure of lists, indents and links.

Important:

- The module supports external widget, but does not guarantee compatibility with any
a third-party library without configuration from the project side;
- legal documents still require meaningful review after
visual editing;
- if the editor generates complex HTML, it is better to check in advance how it
affects display, printing, and PDF export.

## When is it better not to use WYSIWYG?

Stay on `markdown` or `plain_text` if:

- texts are edited by a technical team;
- Predictable diff and a clear history of changes are more important;
- external dependencies need to be minimized;
- the document mainly consists of simple paragraphs, lists and headings.

## How to link a document to an application form

Reliable practical minimum:

- commit `purpose_code`;
- commit `document_code`;
- fix `form_code` if flow is form dependent;
- before submitting the form, call `get_consent_status(...)`;
- after successful confirmation call `accept_consent(...)`;
- for anonymous scripts, store `anonymous_token`.

A detailed step-by-step example is already given in
[operations-admin.md](./operations-admin.md).

## What belongs to the module and what to the project

The consent module is responsible for:

- storage and versioning;
- publication of editorials;
- linking consent to the editorial office;
- API and service layer;
- audit trail.

The integrator project is responsible for:

- the actual legal content of the text;
- choice of editorial process;
- connecting external WYSIWYG, if needed;
- project rules for publication and approval of texts.

## Related documents

- [Use and Administration](./operations-admin.md)
- [Settings and policy contract](./configuration.md)
- [Public service API](./service-api.md)
- [Experimental Confirmed Consent Contour](./verified-flow.md)
