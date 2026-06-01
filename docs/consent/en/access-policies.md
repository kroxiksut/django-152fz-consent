# Consents Module: Access Policies and Resource Scope

- [To the consent section](./README.md)
- [To the general documentation section](../README.md)

## Purpose

The access policy layer augments the consent lifecycle with restrictions on resource actions.

## Recommended Resource Code Contract

Format: `<module>.<resource_action>`, for example:
- `crm.contact_update`
- `billing.invoice_export`
- `support.ticket_view`

For additional grouping, it is acceptable to use `extra_meta`, for example:
- `{"module_scope": "billing", "subsystem": "invoices"}`

## Restrictions

- The access policy layer is optionally enabled via `enable_access_policies`.
- It does not replace the underlying `purpose + document` threading model, but rather works on top of it.
- Access checks should be based on the service layer and documented policy rules.
