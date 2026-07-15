# Hebrew i18n — follow-up

This PR covers the shared chrome (navbar, sidebar, add/edit item+box modal,
card dropdown, delete confirmation, core toasts) and the standalone auth
pages (login, register, onboarding, workspace-pending). Scoped down from
"translate everything" after flagging the full-coverage effort/risk
trade-off — see PR description.

Not yet translated (English strings remain when Hebrew is selected):

- **Content pages** extending `base.html`: `index.html`, `items.html`,
  `item_detail.html`, `box_detail.html`, `box_public.html`, `search.html`,
  `error.html` — page headings, filter labels, stat cards, empty states,
  card badges ("No box", quantity ×N, etc.), and the history-feed JS strings
  (`relTime`, `entryText` — "3 min ago", "Created by X", etc.).
- **Admin modals** in `base.html`: Manage Locations, Workspace Settings
  (name/invite-code/members), Pending Join Requests — including their
  toasts (invite code copied, role updated, request approved/rejected,
  location added/deleted).
- **Backend error messages**: `err.error` strings returned by the Flask
  backend (e.g. validation errors) are English-only; the frontend shows them
  verbatim regardless of UI language. Localizing these needs either backend
  message keys or frontend-side mapping.
- **Pluralization**: English-specific suffix logic (`'s' if count != 1`,
  `'es' if ...`) is baked directly into a few templates. Hebrew plural
  grammar doesn't map onto that pattern — needs real handling, not just a
  translated noun, wherever it's tackled.
- **`<title>` tags**: browser-tab titles per page are still hardcoded
  English (low priority, not user-facing chrome).

ai-tagging language awareness (passing the UI language into the
`suggest-tags` → Bedrock prompt) is intentionally not part of this PR either,
per the explicit requirement to defer it to a later PR alongside workspace
settings.
