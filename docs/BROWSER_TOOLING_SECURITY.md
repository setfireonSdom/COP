# Browser tooling security boundary

Date: 2026-11-03.

## What changed and why

The installed `playwright-core@1.64.1` browser manifest pins Chromium
**156.0.8078.4**, below the **156.0.8078.73** fix boundary identified for:

| Advisory | Area |
|---|---|
| [CVE-2026-118306](https://nvd.nist.gov/vuln/detail/CVE-2026-118306) | FileSystem |
| [CVE-2026-118331](https://nvd.nist.gov/vuln/detail/CVE-2026-118331) | FileAPI |
| [CVE-2026-118344](https://nvd.nist.gov/vuln/detail/CVE-2026-118344) | Layout |
| [CVE-2026-118348](https://nvd.nist.gov/vuln/detail/CVE-2026-118348) | Skia |

Playwright's `chromiumSandbox` option **defaults to `false`**. Repository test
entrypoints explicitly request sandboxing; an option is not proof that all OS
isolation mechanisms are effective.

Verified locally, not assumed:

- `playwright-core/browsers.json` in 1.64.1 pins `156.0.8078.4`.
- The type definition states `chromiumSandbox?: boolean` → `Defaults to false`.
- System Chrome reported `156.0.8078.80` during the earlier check. Each new run
  checks the actual launched version again.
- The default local browser cache was absent at the earlier inspection. That
  does **not** prove browsers were never installed or exclude a custom cache.

Installing this test package does not itself install its browser. Do not run
`playwright install` to provision Chromium for this repository.

## The boundary now enforced

1. **System Chrome allowlist.** `safe-browser.mjs` accepts only `chrome`,
   `chrome-beta`, `chrome-dev`, and `chrome-canary`. Bundled aliases such as
   `chromium-headless-shell` are rejected before launch. There is no fallback.
2. **One policy.** Nine UI regression scripts and the worker-scoped browser
   fixture in `e2e/fixtures.ts` call `launchChrome()`. The runner config obtains
   channel/sandbox options from the same module. This is test tooling, not a
   product dependency.
3. **Sandbox requested.** The launcher passes `chromiumSandbox: true` and exposes
   no arbitrary launch flags or executable-path override.
4. **Four-component version check before any page.** After launch, unknown,
   malformed, or older-than-floor versions are rejected and the browser is
   closed. This floor addresses the identified advisories, not future CVEs.
5. **CI preflight uses the same launcher.** It launches and closes system Chrome
   without creating a page. Printing a version or finding a Chromium binary is
   not sufficient. CI sets `PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1`; it never runs
   the bundled browser installer. The test dependency is pinned exactly.

## Architecture impact: none on product code

Browser policy changes are confined to web test scripts, tests, E2E fixtures and
configuration, the test dependency lock, and CI.

- No file under `apps/web/app`, `apps/web/components`, `apps/web/lib`,
  `packages/`, or `backend/app` imports Playwright.
- The backend has no reference to it.
- The browser policy does not change product contracts or published artifacts.

The dependency direction stays one-way: tests depend on the app, never the
reverse. Adding a guard inside the test layer is therefore a leaf change, not an
architectural one.

## What this does not claim

- It does not make an outdated system Chrome safe. The version guard fails the
  run; it cannot patch the browser.
- It does not audit the rest of the dependency tree. The registry mirror in use
  has no audit endpoint, so `pnpm audit` is unavailable here.
- It does not prevent a person from invoking Playwright directly or installing
  browsers elsewhere. Its enforcement covers repository test entrypoints.
- It does not claim the absence of a default cache proves no past exposure.

## Reproducing the checks

```bash
# Guard regression tests use mocked browsers and make no browser launch
cd apps/web
pnpm exec vitest run tests/browser-security.test.ts

# Real system Chrome preflight, no server required
node scripts/check-browser-security.mjs

# Isolated draft UI with mocked API, no real project writes/server required
node scripts/check-draft-review-ui.mjs

# Full E2E still needs a separately authorised disposable local stack
pnpm test:e2e
```
