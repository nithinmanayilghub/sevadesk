# Story 2.6 — Choose light or dark theme Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (STANDARD-heavy story, per CLAUDE.md §4; Sonnet writes, Opus reviews). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A logged-in User picks System, Light, or Dark on Settings → Appearance; the app changes at once, the choice is saved on their User row, and it comes back on any device. Public pages follow the device only.

**Architecture:** `accounts` owns a new column `users.theme` (`system` | `light` | `dark`, default `system`). `GET /api/v1/me` (and log-in / invite-accept, which return the same `MeResponse`) now include `theme`; a new `PUT /api/v1/me/theme` saves it. In the browser, one attribute decides the theme: `<html data-theme="light|dark">`. No attribute = follow the device. Only the `/app` layout sets the attribute (from `/me`), and it removes it when it unmounts, so public pages never get it. CSS tokens use the native `light-dark()` function with `color-scheme`, so each token is written once (light value, dark value), and the Tailwind `dark:` variant follows the same rule.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy, Alembic, pytest + testcontainers; Next.js 16, React 19, Tailwind 4, Vitest, openapi-typescript.

**Spec:** `_bmad-output/planning-artifacts/epics.md` → "Story 2.6: Choose light or dark theme". Also UX-DR3 (epics.md:132), EXPERIENCE.md line 22 (Themes), line 44 (screen row `Settings → Appearance` · `/app/settings/appearance` · All Roles · from "More"), line 105 (Theme toggle). Architecture review note R-15 (review-reconcile-rubric.md:176): "needs a user preference field owned by `accounts`".

## Global Constraints

- Theme values, exactly: `system`, `light`, `dark`. Default `system` for every User (old and new).
- Saved per **User** (on `users`, a global table), not per Business or per device. No `localStorage`.
- Route `/app/settings/appearance`, open to **all** Roles: NO row in `frontend/src/lib/access.ts` `PAGE_RULES`. Link label `Appearance` on the More page.
- Option labels, verbatim: `System`, `Light`, `Dark`. Group label: `Theme`.
- Save error copy, verbatim: `Could not save. Please try again.`
- Public pages (`/`, `/login`, `/signup`, `/invite/*`, later the Chat Page) never set `data-theme`: device only.
- Dark background keeps the bottom-heavy gradient (`#09090b` → `#000000`, DESIGN.md).
- Tap targets ≥ 44px, visible focus ring, text labels (UX-DR31). Theme color change is instant (no new motion).
- New route must be listed in `tests/integration/test_tenant_isolation.py` (`ISOLATION_CHECKS`), or CI fails.
- `frontend/openapi.json` and `src/api/schema.d.ts` regenerated in WSL only (CI runs `git diff --exit-code`).
- Backend tests run in WSL: `wsl --cd "<repo>/backend" uv run pytest …`. Docker Desktop must run.
- Branch `story/2-6-choose-theme`. PR body ends with `Closes #13`.

## Decisions made in this plan

- **Storage = a column on `users`** (not a new table, not `localStorage`). The AC "another device uses the saved theme" needs the server. One column is the smallest thing that does it.
- **`PUT /api/v1/me/theme`, body `{"theme": "dark"}`, answers 204.** PUT because it sets one value; saying it twice gives the same result.
- **`light-dark()` CSS** instead of two copies of every token. Supported in Chrome 123+, Safari 17.5+, Firefox 120+, which fits UX-DR35 "recent" browsers. Bonus: `color-scheme` also makes scrollbars and native form controls match.
- **Known small flash:** on a full page load of `/app`, the loading block shows in the device theme until `/me` answers (well under a second). Fixing it needs a cookie or `localStorage` plus an inline script. Not in the story; note for later.
- **Controls are disabled while one save runs**, so two quick taps cannot save out of order (same rule as the Team page).

## Review Focus

1. **Save fails (network down, 500, session expired)** → the theme goes back to the old choice and the page shows `Could not save. Please try again.` (a 401 still sends the User to /login via the API client). → Task 4 test.
2. **User leaves `/app` by client-side navigation** (e.g. a link to `/`) → `data-theme` is removed, so the public page follows the device. → Task 3 unmount test.
3. **A bad value** (`"blue"`, missing field) → 422, nothing saved; the database also refuses it (CHECK constraint). → Tasks 1 and 2 tests.
4. **User A saves Dark** → User B (another Business) still has `system`. → Task 2 isolation check.
5. **`dark:` utilities and tokens disagree** (e.g. device dark, User chose Light, but buttons still use `dark:` styles) → both follow the same rule. → Task 3 built-CSS check + manual check in Task 5.

---

### Task 0: Start the story (no code)

- [ ] Show the Story Map (CLAUDE.md §2) and get the User's prediction.
- [ ] `git switch -c story/2-6-choose-theme` from an up-to-date `main`. Add label `in-progress` to issue #13.
- [ ] `sprint-status.yaml`: `2-6-choose-light-or-dark-theme: in-progress`.

---

### Task 1: `users.theme` column (CORE: data model)

**Files:**
- Modify: `backend/app/modules/accounts/schemas.py` (add `Theme`)
- Modify: `backend/app/modules/accounts/models.py` (`User.theme`)
- Create: `backend/migrations/versions/0005_user_theme.py`
- Test: `backend/tests/integration/test_theme.py` (new)

**Interfaces:**
- Produces: `class Theme(StrEnum): SYSTEM = "system"; LIGHT = "light"; DARK = "dark"` in `schemas.py`. `User.theme: Mapped[str]` with `server_default="system"`, and `CheckConstraint("theme IN ('system','light','dark')", name="theme_valid")` in `User.__table_args__`.
- Migration `0005` (down_revision `"0004"`): `op.add_column("users", sa.Column("theme", sa.Text(), server_default="system", nullable=False))` + `op.create_check_constraint("ck_users_theme_valid", "users", "theme IN ('system','light','dark')")`. Downgrade drops both. Names written by hand, as in 0004.

- [ ] **Step 1: Write the failing tests** in `test_theme.py`:
  - `test_new_user_theme_is_system(sign_up_owner)`: sign up; read the `users` row directly (`get_engine()`); `theme == "system"`.
  - `test_database_refuses_unknown_theme(sign_up_owner)`: `UPDATE users SET theme = 'blue'` raises `sqlalchemy.exc.IntegrityError`.
- [ ] **Step 2: Run** `wsl --cd "<repo>/backend" uv run pytest tests/integration/test_theme.py -v` → FAIL (no column).
- [ ] **Step 3: Add** `Theme`, `User.theme`, migration 0005.
- [ ] **Step 4: Run** `test_theme.py` and `test_migrations.py` → PASS (downgrade to base and back still works).
- [ ] **Step 5: Commit** `feat(accounts): users.theme column (story 2.6)`.

---

### Task 2: Read and save the theme over the API (STANDARD)

**Files:**
- Modify: `backend/app/modules/accounts/schemas.py` (`MeResponse.theme`, `ThemeUpdate`)
- Modify: `backend/app/modules/accounts/repository.py` (`UserRepository.get_theme`, `set_theme`)
- Modify: `backend/app/modules/accounts/service.py` (`get_theme`, `set_theme`)
- Modify: `backend/app/modules/accounts/router.py` (`_me`, new route)
- Modify: `backend/tests/integration/test_tenant_isolation.py` (`check_theme`)
- Regenerate: `frontend/openapi.json`, `frontend/src/api/schema.d.ts`
- Test: `backend/tests/integration/test_theme.py`

**Interfaces:**
- Consumes: `Theme`, `User.theme` (Task 1).
- Produces:
  - `MeResponse.theme: Theme` (new field; log-in, invite-accept and `/me` all return it).
  - `class ThemeUpdate(BaseModel): theme: Theme`.
  - `UserRepository.get_theme(user_id: uuid.UUID) -> Theme` and `UserRepository.set_theme(user_id: uuid.UUID, theme: Theme) -> None` (a direct `UPDATE … WHERE id = :user_id`; no system scope: it touches only the caller's own row).
  - `service.get_theme(session, user_id) -> Theme`, `service.set_theme(session, user_id, theme) -> None`. No commit in service (AD-15).
  - Router: `_me(session: Session, actor: Actor) -> MeResponse` (now reads the theme). `@router.put("/me/theme", status_code=204, operation_id="set_theme", responses={401: _ERROR, 422: _ERROR})` → `def set_theme(body: ThemeUpdate, session: SessionDep, actor: ActorDep) -> None`.
  - Frontend type (after regen): `components["schemas"]["Theme"]`.

- [ ] **Step 1: Write the failing tests** in `test_theme.py`:
  - `test_me_starts_with_system(sign_up_owner)`: `GET /api/v1/me` → `json()["theme"] == "system"`.
  - `test_saved_theme_comes_back_on_another_device(make_client)`: sign up with a known email; `PUT /api/v1/me/theme {"theme": "dark"}` → 204; a NEW client logs in with the same email and password → the log-in body has `theme == "dark"` and its `GET /api/v1/me` has `theme == "dark"`.
  - `test_unknown_theme_is_422_and_nothing_changes(sign_up_owner)`: PUT `{"theme": "blue"}` → 422; PUT `{}` → 422; `/me` theme still `"system"`.
  - `test_set_theme_needs_login(client)`: PUT with no session → 401.
- [ ] **Step 2: Add** `check_theme` to `ISOLATION_CHECKS` under key `("PUT", "/api/v1/me/theme")`: A PUTs `"dark"` → 204; A's `/me` theme `"dark"`; B's `/me` theme `"system"`.
- [ ] **Step 3: Run** `test_theme.py` + `test_tenant_isolation.py` → FAIL.
- [ ] **Step 4: Implement** schemas, repository, service, router.
- [ ] **Step 5: Run** full backend suite: `wsl --cd "<repo>/backend" uv run pytest` → PASS. Also `uv run lint-imports` (other modules still import only through `service.py` / `dependencies.py`).
- [ ] **Step 6: Regenerate** in WSL: `uv run python -m app.export_openapi ../frontend/openapi.json`, then in `frontend`: `npm run gen:api`. Run `npm run typecheck` → fix any test fixtures that build a `MeResponse` without `theme` (e.g. `OWNER` / `TECHNICIAN` in `app/app/layout.test.tsx`: add `theme: "system"`).
- [ ] **Step 7: Commit** `feat(accounts): GET /me returns theme; PUT /me/theme saves it (story 2.6)`.

---

### Task 3: The theme switch in the browser (CORE: how the theme is applied)

**Files:**
- Modify: `frontend/src/app/globals.css`
- Create: `frontend/src/lib/theme.tsx`
- Modify: `frontend/src/app/app/layout.tsx`
- Test: `frontend/src/lib/theme.test.tsx` (new), `frontend/src/app/app/layout.test.tsx`

**Interfaces:**
- Consumes: `components["schemas"]["Theme"]` (Task 2), `/me` `data.theme`.
- Produces (in `lib/theme.tsx`):
  - `export type Theme = components["schemas"]["Theme"]`.
  - `export function applyTheme(theme: Theme | null): void` — `"light"`/`"dark"` → `document.documentElement.dataset.theme = theme`; `"system"` or `null` → delete `dataset.theme`.
  - `export function ThemeProvider({ theme, setTheme, children })` and `export function useTheme(): { theme: Theme; setTheme: (theme: Theme) => void }`. Default context (no provider): `{ theme: "system", setTheme: () => {} }`.
- Layout: keeps `const [theme, setTheme] = useState<Theme>("system")`, sets it from `data.theme`; `useEffect(() => { applyTheme(theme); return () => applyTheme(null); }, [theme])`; wraps children in `ThemeProvider` next to `PermissionsProvider`.

CSS (the one part the tests cannot check; keep it exactly this shape):

```css
/* dark: utilities. Chosen theme wins; with no choice, follow the device. */
@custom-variant dark {
  &:where([data-theme="dark"], [data-theme="dark"] *) { @slot; }
  @media (prefers-color-scheme: dark) {
    &:where(:root:not([data-theme="light"]), :root:not([data-theme="light"]) *) { @slot; }
  }
}

:root { color-scheme: light dark; }          /* no choice: the device decides */
:root[data-theme="light"] { color-scheme: light; }
:root[data-theme="dark"]  { color-scheme: dark; }
```

Then every token in `:root` becomes `light-dark(<light>, <dark>)` with today's two values (e.g. `--background: light-dark(#f4f4f5, #09090b);`), the `@media (prefers-color-scheme: dark) :root {…}` block is deleted, and the body gradient becomes `background: linear-gradient(to bottom, var(--background), var(--background-end)) fixed;` with a new token `--background-end: light-dark(#f4f4f5, #000000);` (flat in light, the DESIGN.md gradient in dark). Update the file's header comments.

- [ ] **Step 1: Write the failing tests.**
  - `theme.test.tsx`: `applyTheme("dark")` → `document.documentElement.dataset.theme === "dark"`; `applyTheme("light")` → `"light"`; `applyTheme("system")` → `undefined`; `applyTheme(null)` → `undefined`.
  - `layout.test.tsx`: `/me` answers `theme: "dark"` → after render, `<html>` has `data-theme="dark"`; `theme: "system"` → no `data-theme`; render with `"dark"`, then `unmount()` → no `data-theme` (Review Focus 2). Reset `dataset.theme` in `beforeEach`.
- [ ] **Step 2: Run** `npm test -- theme layout` (in `frontend`) → FAIL.
- [ ] **Step 3: Implement** `lib/theme.tsx`, the layout change, and the CSS.
- [ ] **Step 4: Run** `npm test`, `npm run lint`, `npm run typecheck` → PASS.
- [ ] **Step 5: Check the built CSS** (Review Focus 5): `npm run build`, then search `.next/static/**/*.css` for `data-theme` and `light-dark(`. Expect both, and a `prefers-color-scheme:dark` rule that contains `:not([data-theme=light])`.
- [ ] **Step 6: Commit** `feat(app): data-theme switch with light-dark() tokens (story 2.6)`.

---

### Task 4: Settings → Appearance page (STANDARD)

**Files:**
- Create: `frontend/src/components/AppearanceSettings.tsx`
- Create: `frontend/src/app/app/settings/appearance/page.tsx` (metadata title `Appearance · SevaDesk`, `<h1>Appearance</h1>`, renders `AppearanceSettings`; same layout classes as the Team page)
- Modify: `frontend/src/components/SettingsLinks.tsx` (add `{ href: "/app/settings/appearance", label: "Appearance" }`; update the comment)
- Test: `frontend/src/components/AppearanceSettings.test.tsx` (new), `frontend/src/components/SettingsLinks.test.tsx`

**Interfaces:**
- Consumes: `useTheme()` (Task 3), `api.PUT("/api/v1/me/theme", { body: { theme } })` (Task 2).
- Produces: `export function AppearanceSettings(): JSX.Element` — a `<fieldset>` with `<legend>Theme</legend>` and three native radio inputs (`name="theme"`), labels `System` / `Light` / `Dark`, each label row `min-h-11` (44px). Checked = `useTheme().theme`.

On change to a new value: remember the old value → `setTheme(new)` at once → disable the three radios → `await api.PUT(...)`. If `response.ok` is false or it throws: `setTheme(old)` and show `<p role="alert">Could not save. Please try again.</p>`. Re-enable in `finally`. Clear the message on the next change.

- [ ] **Step 1: Write the failing tests** (`AppearanceSettings.test.tsx`; mock `@/api/client`, render inside `ThemeProvider` with a real `useState` wrapper):
  - `shows the saved choice`: provider theme `"dark"` → radio `Dark` is checked.
  - `applies at once and saves`: click `Light` → radio `Light` checked before the PUT resolves; `PUT` called with `"/api/v1/me/theme", { body: { theme: "light" } }`.
  - `goes back and says so when the save fails`: PUT resolves `{ response: { ok: false } }` → `Dark` checked again and alert text `Could not save. Please try again.`; same when PUT rejects (network down).
  - `one save at a time`: while a PUT is pending, all three radios are disabled.
  - `SettingsLinks.test.tsx`: a User with NO permissions sees the `Appearance` link (all Roles); the Owner sees `Team` and `Appearance`.
- [ ] **Step 2: Run** `npm test -- Appearance SettingsLinks` → FAIL.
- [ ] **Step 3: Implement** the component, page, and link.
- [ ] **Step 4: Run** `npm test`, `npm run lint`, `npm run typecheck` → PASS.
- [ ] **Step 5: Commit** `feat(app): Settings → Appearance page (story 2.6)`.

---

### Task 5: Live check and story status (no new code)

- [ ] Start the stack (see README / the `run` skill). Log in. In the browser, with the device set to light and then dark:
  - More → Appearance → Dark: the whole app turns dark at once, with the gradient. Light: turns light even on a dark device. System: follows the device.
  - Buttons (outline, destructive) look right in each case (Review Focus 5).
  - Reload `/app` → the saved theme comes back. Log in from a private window → the same theme.
  - Open `/` and `/login`: they follow the device only, whatever the User chose.
- [ ] Opus whole-branch review (`superpowers:requesting-code-review`); apply fixes, each with a test.
- [ ] Then CLAUDE.md §5–§7: Understanding Gate, hands-on task, `docs/learning/2-6.md`, glossary terms (`data-theme`, `color-scheme`, `light-dark()`, CSS custom variant). Epic 2 ends with this story: update `docs/learning/architecture-map.md` and ask the User to explain the system in 5 sentences.
- [ ] `sprint-status.yaml` → `done` (and `epic-2: done`); PR with `Closes #13`; remove `in-progress` label after merge.
