# AegisOps SRE & Showcase Console — UI Design Contract (`UI-SPEC.md`)

> **Visual Direction:** High-density technical dark console inspired by Linear & Datadog (`1280px–1920px` desktop-first with responsive `<= 1024px` tablet and `<= 640px` mobile fallbacks).
> **Architecture Standard:** Modular primitives (`components/ui/`), domain features (`features/`), isolated side-effect hooks (`hooks/`), strict TypeScript with zero raw hex values in `.tsx` components.

---

## 1. Semantic Design Tokens (`frontend/src/styles.css`)

| Role | Token | Value | Legacy Alias |
|---|---|---|---|
| Canvas Background (60%) | `--bg-canvas` | `#0b101b` | `--bg` |
| Card / Surface (30%) | `--bg-surface` | `#121a2a` | `--panel` |
| Nested Elevated Tile | `--bg-elevated` | `#0f1624` | `--panel-alt` |
| Subtle Input / Track | `--bg-subtle` | `#090d16` | — |
| Interactive Neutral Surface | `--bg-control` | `#1e293b` | — |
| Subtle Border Hairline | `--border-subtle` | `#25324b` | `--border` |
| Strong Focus / Control Border | `--border-strong` | `#334155` | — |
| Primary Text | `--text-primary` | `#e6edf7` | `--text` |
| Secondary Text | `--text-secondary` | `#cbd5e1` | — |
| Muted Meta Text | `--text-muted` | `#93a4be` | `--muted` |
| Primary Interactive Accent (10%) | `--accent-primary` | `#0284c7` | — |
| Bright Accent Highlight | `--accent-highlight` | `#38bdf8` | `--accent` |
| Success Semantic | `--status-success` | `#10b981` | `--ok` |
| Warning Semantic | `--status-warning` | `#f59e0b` | `--warn` |
| Danger Semantic | `--status-danger` | `#ef4444` | `--err` |
| Info / Replay Semantic | `--status-info` | `#38bdf8` | — |

---

## 2. Typography, Numbers & Spacing Grid

- **UI Font Stack:** `Inter, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif`
- **Monospace Font Stack:** `ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace`
- **Tabular Numerals:** `font-variant-numeric: tabular-nums` enforced globally on `.metric-value`, `.metric-sub`, `.data-table`, `.row-sub`, `.mono-small`, `.badge`, and live timers/latencies.
- **Spacing Scale (`4px / 8px` Grid):** `--space-1: 4px`, `--space-2: 8px`, `--space-3: 12px`, `--space-4: 16px`, `--space-6: 24px`, `--space-8: 32px`, `--space-12: 48px`.
- **Transitions & Motion:** `160ms cubic-bezier(0.2, 0, 0, 1)`, suppressed automatically under `@media (prefers-reduced-motion: reduce)`.

---

## 3. Mandatory 5-State Interaction Matrix

| State | Behavior Enforced Across Console |
|---|---|
| **Loading** | Dimension-matched `<Skeleton />` blocks on shell bootstrap, Metrics strip, Topology viewer, Incident queue, and Engineering Evidence (prevents Cumulative Layout Shift). |
| **Empty** | Structured `<EmptyState />` explaining *why* the queue/table/runbooks are empty plus a direct next CTA (e.g., Sign In, Clear Filters, Launch Recorded Replay). |
| **Error / Stale** | Dismissible/retryable `role="alert"` banner with correlation context + SSE `stale` warning if stream heartbeats pause `> 20s`. |
| **Mutating / Pending** | Disabled trigger + loading label (`Launching...`, `Generating Secret...`, `Restoring...`, `Verifying...`) preventing duplicate submissions. |
| **Destructive / High-Risk** | `<Modal />` with Escape close, focus restoration, explicit blast-radius preview table, `manual_reset_assisted` acknowledgement checkbox, and TOTP action binding. |

---

## 4. Accessibility (WCAG 2.1 AA Baseline) & Preserved E2E Contract

- **Semantic Landmarks:** `<header>`, `<nav>`, `<main>`, `<section>`, `<dialog>` / `role="dialog"` + `aria-modal="true"`, `role="tablist"` + `role="tab"`, `<label>` associations, `aria-describedby` on form errors, visible `:focus-visible` `2px` outlines.
- **Status Independence:** Every status indicator pairs color with explicit text badges (`Healthy`, `Degraded`, `CRITICAL`, `ESCALATED`, `PASS`, `FAIL`).
- **Playwright E2E Selector Continuity:** Preserves 100% of assertions in `backend/tests/e2e/test_browser_console.py` and `backend/tests/e2e/test_showcase_browser.py` verbatim.
