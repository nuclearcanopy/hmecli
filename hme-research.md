# iCloud Hide My Email tools (GitHub, checked 2026-11-20)

| Project | Lang | CLI? | Last push | Notes |
|---|---|---|---|---|
| dedoussis/icloud-hide-my-email-browser-extension | TypeScript | no (browser ext) | 2025-11 | 540★; reference implementation, relies on browser cookies |
| rtunazzz/hidemyemail-generator | Python | yes + macOS app | 2026-10 | 774★; bulk generate, cookie-string auth, China support |
| xiaozhou26/icloud-hme | Go | likely | 2026-09 | 731★, no description |
| glizzykingdreko/icloud-hme | Python | yes | 2026-01 | multi-account generate/manage |
| Yimikami/icloud-hme-manager | JavaScript | yes | 2026-10 | manage HME from command line; tiny |
| D3-vin/icloud-hidemyemail-generator | Go | yes (interactive) | 2026-10 | |
| maxktz/icloud-hidemyemail-generator | Python | yes | 2023-11 | stale |
| heartmore/icloud-hme, banana2556/hme-manager, forever94yu/icloud-prime | Py/Go | web UI/service | 2026 | dashboards/schedulers, not CLI-first |
| ykky0/icloud-hide-my-email-srp | Python | ? | 2026-05 | appears to do SRP login (password) |

Common pattern: all reuse the web endpoints below with a Cookie header copied from a signed-in browser.
None was audited; hmecli reimplements the flow rather than trusting them.
