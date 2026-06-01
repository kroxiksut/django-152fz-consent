# Cookie module: key invariants

- [Go to cookies section](./README.md)
- [To the general documentation section](../README.md)

## Banner state and consent state are different

- Displaying and closing a banner does not equal consent;
- `dismiss` does not create or revoke consent;
- banner status fields (`dismissed_at`, `decided_at`) are maintained separately from consent records.

## Server database - source of truth

- the cookie decision is stored on the server;
- the anonymous record is stored in the database with a token;
- once logged in, anonymous records can be linked to the user.

## Replay and `outdated` are different mechanisms

- `outdated` appears when the relevant policy revision changes;
- repeat display by interval controls only the visibility of the banner;
- spaced repeat exposure does not change consent status by itself.

## Banner texts are separated from the cookie policy

- banner revisions (`CookieBannerRevision`) are published separately from `CookiePolicyRevision`;
- publishing a banner revision does not move consent into `outdated`.
