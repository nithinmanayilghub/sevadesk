---
name: SevaDesk
description: AI front desk for Indian home-service businesses. shadcn/ui on Next.js + Tailwind; this file specifies the brand-layer delta only. Light and dark themes. Glass styling only on the landing page.
status: final
created: 2026-11-01
updated: 2026-11-01
sources:
  - _bmad-output/planning-artifacts/prds/prd-seva-desk-2026-11-01/prd.md
  - _bmad-output/planning-artifacts/briefs/brief-seva-desk-2026-11-01/brief.md
  - docs/project-seed.md
  - imports/user-design-system.json
colors:
  # Brand overrides on top of shadcn defaults. Unlisted tokens (popover, input,
  # ring, destructive, ...) inherit from shadcn. Contrast ratios are on the
  # background named in the comment.
  background: '#F4F4F5'            # zinc-100
  card: '#FFFFFF'
  foreground: '#18181B'            # zinc-900, 16.1:1 on background
  muted-foreground: '#52525B'      # zinc-600, ~7:1 on background (user's #71717A fails at 4.4:1)
  border: '#E4E4E7'                # zinc-200
  primary: '#18181B'               # pill buttons
  primary-foreground: '#FFFFFF'
  accent: '#047857'                # emerald-700, 5.5:1 on white: text, links, confirmed
  accent-foreground: '#FFFFFF'
  accent-soft: '#D1FAE5'           # emerald-100, badge fill
  status-requested: '#B45309'      # amber-700
  status-handoff: '#B91C1C'        # red-700
  background-dark: '#09090B'       # zinc-950
  card-dark: '#18181B'             # zinc-900 (user's zinc accent)
  foreground-dark: '#FAFAFA'
  muted-foreground-dark: '#A1A1AA' # zinc-400
  border-dark: '#27272A'           # zinc-800
  primary-dark: '#FFFFFF'          # pill buttons invert in dark
  primary-foreground-dark: '#18181B'
  accent-dark: '#34D399'           # user's emerald, 10.9:1 on black
  accent-foreground-dark: '#022C22'
  accent-soft-dark: '#064E3B'
  status-requested-dark: '#FBBF24'
  status-handoff-dark: '#F87171'
  landing-black: '#000000'
typography:
  # Inter for Latin; Noto Sans Devanagari for Hindi, loaded only when Hindi text appears.
  display:
    fontFamily: "'Inter', 'Noto Sans Devanagari', system-ui, sans-serif"
    fontSize: clamp(48px, 9vw, 112px)
    fontWeight: '700'
    lineHeight: '1.05'
    letterSpacing: -0.05em
  heading:
    fontFamily: "'Inter', 'Noto Sans Devanagari', system-ui, sans-serif"
    fontSize: 24px
    fontWeight: '600'
    lineHeight: '1.2'
    letterSpacing: -0.02em
  title:
    fontFamily: "'Inter', 'Noto Sans Devanagari', system-ui, sans-serif"
    fontSize: 18px
    fontWeight: '600'
    lineHeight: '1.3'
  body:
    fontFamily: "'Inter', 'Noto Sans Devanagari', system-ui, sans-serif"
    fontSize: 16px
    fontWeight: '400'
    lineHeight: '1.5'
  body-sm:
    fontFamily: "'Inter', 'Noto Sans Devanagari', system-ui, sans-serif"
    fontSize: 14px
    fontWeight: '400'
    lineHeight: '1.45'
  label:
    fontFamily: "'Inter', system-ui, sans-serif"
    fontSize: 12px
    fontWeight: '600'
    lineHeight: '1.2'
    letterSpacing: 0.08em
rounded:
  sm: 8px
  md: 12px
  lg: 16px
  xl: 24px
  section: 40px
  full: 9999px
spacing:
  # Tailwind defaults inherited. Named tokens only:
  page-x-mobile: 16px
  page-x-desktop: 32px
  max-width-app: 1280px
  max-width-landing: 1600px
  tap-target: 44px
components:
  button-primary:
    background: '{colors.primary}'
    foreground: '{colors.primary-foreground}'
    radius: '{rounded.full}'
    height: '{spacing.tap-target}'
  button-action:
    note: 'Pill with nested circular icon (from user design system). Landing CTAs and the Booking Request Confirm action only.'
    background: '{colors.primary}'
    foreground: '{colors.primary-foreground}'
    icon-container: '40px circle, {colors.card} on light / {colors.card-dark} on dark'
    radius: '{rounded.full}'
  card:
    background: '{colors.card}'
    border: '1px solid {colors.border}'
    radius: '{rounded.lg}'
  status-badge:
    radius: '{rounded.full}'
    typography: '{typography.label}'
  chat-bubble-customer:
    background: '{colors.primary}'
    foreground: '{colors.primary-foreground}'
    radius: '{rounded.xl}'
  chat-bubble-agent:
    background: '{colors.card}'
    foreground: '{colors.foreground}'
    border: '1px solid {colors.border}'
    radius: '{rounded.xl}'
  glass-panel:
    note: 'Landing page only.'
    background: 'rgba(255, 255, 255, 0.05)'
    backdrop-filter: 'blur(12px)'
    border: '1px solid rgba(255, 255, 255, 0.1)'
    radius: '{rounded.xl}'
  landing-section:
    radius: '{rounded.section}'
    background-dark: 'linear-gradient(180deg, #18181B 0%, #000000 100%)'
---

## Brand & Style

SevaDesk is a calm, dependable front desk for busy tradespeople. The brand posture is **"premium tool, not a toy"**: monochrome zinc surfaces, one emerald accent that means *done or confirmed*, Inter type, and generous rounded shapes. It comes from the user's glassmorphism design system (`imports/user-design-system.json`).

There are two expressions of one brand:
- **Landing page:** the full design system. Dark, immersive sections, glass panels, a grain texture, large display type, and entry motion. It sells the project to recruiters.
- **App screens** (Chat Page, Inbox, Calendar, Dashboard, settings): the same colors, type, and shapes, but **solid surfaces only**. No glass, no grain, no blur. These screens are read on cheap phones, on slow networks, and in sunlight.

SevaDesk inherits shadcn/ui. This file specifies only the brand delta: colors, Inter plus Devanagari, larger radii, pill buttons, status badges, chat bubbles, and the landing-only glass tokens.

Visual references: [Chat Page](mockups/key-chat-page.html), [Dashboard](mockups/key-dashboard.html), [Landing page hero](mockups/key-landing-hero.html). This file wins over the mocks on conflict.

## Colors

- **Zinc neutrals** carry 90% of every screen. `{colors.background}` / `{colors.card}` in light mode and `{colors.background-dark}` / `{colors.card-dark}` in dark mode.
- **Primary (zinc-900 / white)** is for main buttons and Customer chat bubbles. It inverts in dark mode, as in the user's button spec.
- **Emerald** means *confirmed, positive, done*: confirmed Bookings, success toasts, links, and the active nav item. On light surfaces, use `{colors.accent}` (#047857). The user's `#34D399` is used **only on dark surfaces** (`{colors.accent-dark}`). On white it has only 1.9:1 contrast.
- **Amber (`{colors.status-requested}`)** means *waiting*: Booking Requests and the 12-hour countdown.
- **Red (`{colors.status-handoff}`)** means *a human must act*: Needs Human Conversations. Destructive actions use shadcn's `destructive`.
- **Body text** uses `{colors.muted-foreground}` (zinc-600), not the user's zinc-500. Zinc-500 on zinc-100 is 4.4:1, which is below WCAG AA (4.5:1).

## Typography

- **Inter** for all Latin text. **Noto Sans Devanagari** is the fallback for Hindi. Inter has no Devanagari glyphs. The Devanagari font loads only for the characters on the page (`unicode-range`), so English-only pages do not pay for it.
- `{typography.display}` is used only on the landing page, with the user's -0.05em tracking and 1.05 leading.
- App headings use `{typography.heading}` and `{typography.title}` with softer tracking (-0.02em). Tight tracking hurts small sizes.
- Body weight is **400**, not 300. Light weights blur on low-DPI phones and in Devanagari.
- Labels use `{typography.label}` at **12px**, uppercase. This replaces the user's 10px. 10px is too small to read on phones.
- Money uses Indian digit grouping: ₹1,499 and ₹1,00,000.

## Layout & Spacing

- The app is mobile-first from 360px. Side padding is `{spacing.page-x-mobile}`, and `{spacing.page-x-desktop}` from 1024px. The app content width is at most `{spacing.max-width-app}`.
- The landing page uses `{spacing.max-width-landing}` (1600px), as in the user's spec.
- Every tappable element is at least `{spacing.tap-target}` (44px) high.

## Elevation & Depth

- **App:** depth comes from tone, not shadows. A card sits on the background with a 1px `{colors.border}`. Sheets and dialogs use shadcn's default shadow.
- **Dark app background:** a subtle bottom-heavy gradient from `{colors.background-dark}` to black. This keeps the user's "no flat dark backgrounds" rule. A CSS gradient costs almost nothing.
- **Landing:** glass panels (`components.glass-panel`) over dark gradient sections, with the grain overlay at 15% opacity.

## Shapes

- `{rounded.section}` (40px): landing page section wrappers only. This is the user's "2.5rem rhythm" rule.
- `{rounded.lg}` (16px): app cards and the Booking Request card.
- `{rounded.xl}` (24px): chat bubbles and glass panels.
- `{rounded.md}` (12px): inputs and selects.
- `{rounded.full}`: buttons, badges, Slot chips, and quick-reply chips.

## Components

- **Button primary:** a pill, `{colors.primary}`, 44px high. Hover changes the background color in 150ms. The app has no scale effect on hover.
- **Button action** (the user's pill with a nested icon circle): for landing CTAs and the **Confirm** button on a Booking Request. Hover on the landing page scales it to 105%. In the app it only changes color.
- **Status badge:** a pill with a label and an icon. Confirmed = emerald, requested = amber, Needs Human = red, expired/declined/cancelled = zinc. Each badge also has an icon and text, so meaning never depends on color alone.
- **Chat bubbles:** Customer messages are on the right in `{colors.primary}`. Agent and User messages are on the left on `{colors.card}`. A User (human) reply shows the User's name above the bubble, so the Customer knows that a person is answering.
- **Service price row (Chat Page):** the Service name, "from ₹X" in `{typography.title}`, and the duration in `{typography.body-sm}` muted.
- **Glass panel / glass stat card:** landing page only. 1px white/10% border, as the user's spec requires.

## Do's and Don'ts

- **Do** use glass, grain, blur, the 22vw background word, and fade-in-up motion **only on the landing page**.
- **Do** keep app screens solid, so they meet the 200 KB Chat Page budget and stay readable in sunlight.
- **Don't** put `#34D399` text or buttons on light surfaces. Use `{colors.accent}`.
- **Don't** use font weight 300, or labels below 12px.
- **Don't** use emerald for decoration. It means *confirmed*.
- **Don't** use stock photos on the landing hero. Use a CSS or SVG gradient instead, to keep the page under 1 MB.
