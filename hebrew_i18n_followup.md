# Hebrew i18n — follow-up

Originally scoped down from "translate everything" in PR #8 after flagging
the full-coverage effort/risk trade-off. Since then:

- PR #8: shared chrome (navbar, sidebar, add/edit item+box modal, card
  dropdown, delete confirmation, core toasts) + standalone auth pages
  (login, register, onboarding, workspace-pending).
- PR #9: workspace tag-language preference (Settings modal selector) +
  ai-tagging language-aware prompts — the "defer ai-tagging language
  awareness" note from the original version of this file is stale, that
  landed.
- This pass: content pages (`index.html`, `items.html`, `item_detail.html`,
  `box_detail.html`, `box_public.html`, `search.html`, `error.html`) —
  headings, filter labels, stat cards, empty states, card badges, the
  history-feed JS strings (`relTime`/`entryText`), and the `Box not
  found`/`Item not found`/"workspace name required"/"failed to create
  workspace" messages the frontend itself generates. Tag-language selector
  added to the workspace *creation* form (previously Settings-modal only).

Still not translated (English strings remain when Hebrew is selected):

- **Admin modals** in `base.html`: Manage Locations, Workspace Settings
  (name/invite-code/members), Pending Join Requests — including their
  toasts (invite code copied, role updated, request approved/rejected,
  location added/deleted).
- **Backend-returned error messages**: `err.error` strings that originate
  from the Flask *backend*/*auth-service* (e.g. "X already exists",
  validation errors) are English-only; the frontend shows them verbatim
  regardless of UI language. Localizing these needs backend message keys
  or a frontend-side mapping — different from the frontend-generated
  messages (now translated) like "Box not found".
- **Pluralization is a simplified singular/plural split, not full Hebrew
  grammar.** Content pages now pick between two translated noun forms
  (e.g. `item_singular`/`item_plural`) instead of the old English `'s'`
  suffix hack, which is the correct *shape* for Hebrew (no `-s` grammar to
  begin with) — but doesn't handle Hebrew's dual form or construct-state
  nouns. Acceptable for a UI count display, not linguistically complete.
- **Relative time strings** (`just now`, `{n} min/h/d ago`) use simplified
  Hebrew phrasing (e.g. "לפני X דקות") without proper singular/dual/plural
  agreement (1 minute vs. 2 minutes vs. 5 minutes take different Hebrew
  forms) — same simplification tradeoff as above.
- **`<title>` tags**: browser-tab titles per page are still hardcoded
  English (low priority, not user-facing chrome).
