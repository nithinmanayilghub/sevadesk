# Refactor — One route registry for /app pages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (native build, per CLAUDE.md §4). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every `/app` page is one row in one list (`frontend/src/lib/pages.ts`). The tabs, the settings links, `canOpen` and `landingPath` all read that list.

**Architecture:** A new module `lib/pages.ts` holds `PAGES` (one record per page: href, label, needed permission, place) and five small functions that read it. It replaces `lib/access.ts`, `lib/nav.ts`, the `SETTINGS` list in `SettingsLinks.tsx` and `landingPath` in `lib/auth.ts`. A path with no row is now **blocked** (fail closed). A test checks that each `page.tsx` under `app/app` has a row. Display only: the backend still answers 403 (AD-5).

**Tech Stack:** Next.js 16, React 19, TypeScript, lucide-react, Vitest (`import.meta.glob` from Vite).

**Spec:** Design decisions made with the user on 2026-11-18 (this session, 4 questions). Background: architecture review candidate "one route registry for /app pages". UX-DR16 (nav), UX-DR18 (landing), UX-DR27 (hide what a Role cannot use).

## Global Constraints

- No visible change for any Role today. Same tabs, same order, same labels, same icons, same settings links, same landing page.
- Tab order, exactly: Dashboard `/app`, Inbox `/app/inbox`, Calendar `/app/calendar`, More `/app/more` (More also current under `/app/settings`).
- Settings order, exactly: Team `/app/settings/team`, Appearance `/app/settings/appearance`.
- Rules, exactly: `/app` needs `see_dashboard`; `/app/inbox` needs `use_inbox_and_bookings`; `/app/settings/team` needs `manage_setup`. Calendar, More, Appearance: no `needs` (all Roles).
- `isUnder` rule unchanged: `/app` matches only itself; other hrefs match themselves and sub-paths (`/app/inbox/123`), never look-alikes (`/app/inboxes`).
- Run in `frontend`: `npm test`, `npm run lint`, `npm run typecheck`.
- Branch `refactor/route-registry`. No GitHub issue (not a story); PR body says so.

## Decisions made in this plan

- **Every page has a row** (user choice 1). A page with no `needs` is open to all Roles.
- **No row = blocked** (user choice 2). `canOpen` returns `false` for an unknown path. A wrong URL like `/app/foo` shows "No access", not "Not found". Accepted.
- **`landingPath` = first tab the User may open** (user choice 3). It walks the tabs in order. Owner/Staff → `/app`; Technician → `/app/calendar`. If no tab is open (cannot happen: Calendar has no `needs`), return `/app/calendar`.
- **One file `lib/pages.ts`** (user choice 4). `Permission` type moves there too. `lib/access.ts` and `lib/nav.ts` are deleted. `lib/auth.ts` keeps only `shouldRedirectToLogin`.
- **`alsoActiveUnder` stays a field on the More row.** Not derived from `place: "settings"`: one explicit field is simpler than a hidden rule.

## Review Focus

1. A future page folder with no row → it must show "No access", and the "every page has a row" test must fail. (Task 1 tests both.)
2. A sub-page of a locked page (`/app/inbox/123`, later `/app/settings/services/5`) → same rule as its parent. (Task 1 test.)
3. A look-alike path (`/app/inboxes`, `/app/settings/teams`) → must not borrow the rule of `/app/inbox` / `/app/settings/team`; with fail-closed it is blocked. (Task 1 test.)
4. `/app/settings` itself (no page) → blocked; More still shows as current there. (Task 1 test for `canOpen`; existing AppShell test covers "current".)
5. Log-in and invite-accept still land on the right page after the move. (Existing `LoginForm` / `AcceptInviteForm` tests; Task 2 runs them.)

---

### Task 1 (CORE): Build `lib/pages.ts` and its tests

**Files:**
- Create: `frontend/src/lib/pages.ts`
- Create: `frontend/src/lib/pages.test.ts`

**Interfaces:**
- Produces (all exported from `@/lib/pages`):
  - `type Permission = components["schemas"]["Permission"]`
  - `type Tab = { href: string; label: string; icon: LucideIcon; alsoActiveUnder?: string[] }`
  - `type SettingsLink = { href: string; label: string }`
  - `PAGES: readonly Page[]` where `Page = { href; label; needs?: Permission } & ({ place: "tab"; icon: LucideIcon; alsoActiveUnder?: string[] } | { place: "settings" })`
  - `isUnder(pathname: string, href: string): boolean` — moved unchanged from `access.ts`
  - `canOpen(pathname: string, permissions: Permission[]): boolean`
  - `tabs(permissions: Permission[]): Tab[]`
  - `settingsLinks(permissions: Permission[]): SettingsLink[]`
  - `landingPath(permissions: Permission[]): string`

- [ ] **Step 1: Write the failing tests** in `pages.test.ts`. Move over every test from `access.test.ts`, `nav.test.ts` (use `tabs` in place of `navItems`) and the two `landingPath` tests from `auth.test.ts`, unchanged in values. Add:

```ts
test("a path with no row is blocked, even for the Owner", () => {
  expect(canOpen("/app/foo", OWNER)).toBe(false);
  expect(canOpen("/app/settings", OWNER)).toBe(false);
  expect(canOpen("/app/inboxes", OWNER)).toBe(false);
  expect(canOpen("/app/settings/teams", OWNER)).toBe(false);
});

test("a sub-page follows its parent's rule", () => {
  expect(canOpen("/app/settings/team/5", ["manage_setup"])).toBe(true);
  expect(canOpen("/app/settings/team/5", STAFF)).toBe(false);
});

test("settings links: Owner sees Team then Appearance; Technician sees Appearance only", () => {
  expect(settingsLinks(OWNER).map((l) => l.label)).toEqual(["Team", "Appearance"]);
  expect(settingsLinks(TECHNICIAN).map((l) => l.label)).toEqual(["Appearance"]);
});

test("every page.tsx under app/app has a row in PAGES", () => {
  // Vite lists the files at test time. "../app/app/settings/team/page.tsx" -> "/app/settings/team".
  const files = Object.keys(import.meta.glob("../app/app/**/page.tsx"));
  const hrefs = files.map((f) => f.replace("../app", "").replace(/\/page\.tsx$/, ""));
  expect(hrefs.length).toBeGreaterThan(0);
  expect(PAGES.map((p) => p.href).sort()).toEqual(hrefs.sort());
});
```

  If `npm run typecheck` says `glob` does not exist on `ImportMeta`, add `/// <reference types="vite/client" />` as the first line of `pages.test.ts`.

- [ ] **Step 2: Run** `npm test -- pages` (in `frontend`) → FAIL ("Cannot find module './pages'").
- [ ] **Step 3: Implement `lib/pages.ts`.** Rows in the order Dashboard, Inbox, Calendar, More, Team, Appearance (values from Global Constraints; icons `LayoutDashboard`, `Inbox`, `CalendarDays`, `Ellipsis`). `canOpen`: find the row whose href the path `isUnder`; no row → `false`; row without `needs` → `true`; else `permissions.includes(needs)`. `tabs` / `settingsLinks`: filter by `place`, then by `canOpen`, and return only the fields of their type. `landingPath`: `tabs(permissions)[0]?.href ?? "/app/calendar"`. Top comment: what the file owns, display only (AD-5), "a new page = one new row here".
- [ ] **Step 4: Run** `npm test -- pages` → PASS. `npm run typecheck` → PASS (old files still exist; nothing uses the new one yet).
- [ ] **Step 5: Commit** `refactor(app): one route registry for /app pages (lib/pages.ts)`.
- [ ] **CHECKPOINT** — stop. Walk the user through `pages.ts`: one row, five readers, why fail closed.

### Task 2 (STANDARD): Point every caller at `lib/pages.ts`; delete the old lists

**Files:**
- Modify: `frontend/src/components/AppShell.tsx` (imports; `NavItem` → `Tab`; `navItems` → `tabs`)
- Modify: `frontend/src/components/SettingsLinks.tsx` (delete `SETTINGS`; use `settingsLinks(permissions)`; update top comment: "a new settings page = one row in lib/pages.ts")
- Modify: `frontend/src/app/app/layout.tsx:11` (import `canOpen`, `Permission` from `@/lib/pages`)
- Modify: `frontend/src/components/LoginForm.tsx:11`, `frontend/src/components/AcceptInviteForm.tsx:11` (import `landingPath` from `@/lib/pages`)
- Modify: `frontend/src/lib/permissions.tsx:7`, `frontend/src/components/SettingsLinks.test.tsx:4` (import `Permission` from `@/lib/pages`)
- Modify: `frontend/src/lib/auth.ts` (remove `landingPath` and its `Permission` import), `frontend/src/lib/auth.test.ts` (remove the two `landingPath` tests)
- Delete: `frontend/src/lib/access.ts`, `frontend/src/lib/access.test.ts`, `frontend/src/lib/nav.ts`, `frontend/src/lib/nav.test.ts`
- Modify: `docs/learning/architecture-map.md:89` (row now names `lib/pages.ts`: which pages exist, who may open them, tabs and settings links; display only)

**Interfaces:**
- Consumes: everything Task 1 produces.

- [ ] **Step 1: Make the edits above.** No behaviour change, so the existing tests are the red/green proof (AppShell, SettingsLinks, layout, LoginForm, AcceptInviteForm).
- [ ] **Step 2: Run** `grep -rn "lib/access\|lib/nav\|navItems\|NavItem\|PAGE_RULES" frontend/src` → no output.
- [ ] **Step 3: Run** `npm test`, `npm run lint`, `npm run typecheck` (in `frontend`) → all PASS.
- [ ] **Step 4: Commit** `refactor(app): read tabs, settings links, access and landing from lib/pages.ts`.

### Finish

- [ ] One whole-branch review by an Opus subagent (CLAUDE.md §4).
- [ ] Open the PR (body: what moved, fail-closed change, "no issue: refactor between Epic 2 and Epic 3"). After merge: update memory resume point → Epic 3, Story 3.1 + gaps quiz.
