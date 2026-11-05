# Visual Guides

Standalone public source repository: `JakeIwen/visual-guides`. The local checkout
is `~/dev/visual-guides`; it was extracted from `JakeIwen/scripts` with its four
guide commits preserved. Do not add a second copy to the scripts repository.

## Where things live

- `app.py`: stable service/CLI entry and compatibility exports.
- `visual_guides_server.py`: shared HTTP/static server and guarded A/C API.
- `visual_guides_cli.py`: argument parsing, preview/send client and server composition.
- `ac_ir.py`: canonical RG15D commands, waveform encoding and IR transport.
- `hardware_setup.py`: explicit Pi GPIO18 setup and hardware activation.
- `deploy.py`, `visual-guides.service`: immutable Pi releases and systemd unit.
- `local_service/model.py`: Mac service constants and ownership record contract.
- `local_service/runtime.py`: loopback-only preview server and graceful shutdown.
- `local_service/launchd.py`: plist generation, ownership and launchctl boundary.
- `local_service/control.py`: status, start/stop/restart, install and verification.
- `static/guides/`: source pages; `static/index.html` is the guide directory.
- `static/assets/palette.css`: all CSS design colors and theme overrides.
- `static/assets/site.css`: shared typography, guide primitives and responsive layout.
- `static/guides/<name>.css`, `<name>.js`: private styles and behavior beside their HTML guide; page URLs remain stable.
- `static/reference/`: versioned supporting documents, refreshed with their guide.
- `static/reference/keyboard-shortcuts.json`: the only public-safe custom keyboard
  catalog; `keyboard-shortcuts.schema.json` owns its versioned record vocabulary.
  `static/guides/keyboard-shortcuts.{html,js,css}` renders it; the standalone
  `keyboard_reference.py` validates, filters and prints it (stdlib Python 3.9+).
  This catalog alone has an approved readable-data size exception: canonical
  shortcut record table shared by the guide and CLI; keeping complete readable
  records together avoids duplicate catalogs. The size checker does not measure
  JSON, so this rationale belongs here rather than in an ineffective config rule.
- `tests/test_keyboard_reference.py`, `tests/keyboard_reference_cases.cjs`: shared
  fixture coverage of catalog validation, browser rendering and CLI/filter parity;
  the Python suite also gates production catalog privacy with tested heuristics.
- `tests/`, `test_deploy.py`, `test_hardware_setup.py`: behavioral verification.
- `tests/test_static_contract.py`: local asset references, private/shared ownership,
  palette ownership and syntax checks for every discovered browser script.

## Hosting and changes

The Pi serves port 8791 using `/home/pi/visual-guides/current`; the Mac serves
loopback port 8792 using `system/com.jacobr.visual-guides`. See
`docs/local-hosting.md`. Inspect live state before deployment. Never edit an
immutable Pi release, copy runtime state into Git, or expose tokens in output.
Both boot services were verified installed/enabled on October 12, 2026; Mac
KeepAlive recovery was proven through a controlled graceful restart. Reinspect
live state, and do not reinstall a healthy service for routine edits.

The Mac is always preview-only. Keep Pi transmission disabled unless explicitly
requested and hardware verified. GPIO17 belongs to a different service. A send
does not confirm appliance state; preserve the no-retry behavior.

Use the scoped Pi deployer here. Dashboard project links are documented in
`~/dev/van-dashboard/docs/HOSTED_PROJECTS.md`: projects live in the dashboard's
runtime StateStore (filled by its scanner and UI), not a static source catalog;
preserve user-added links.

`npm run deploy` is the combined Mac/Pi workflow: check both hosts, run tests,
gracefully restart Mac Python, apply the Pi release, verify Mac supervision.
`npm run deploy:check` is read-only; `npm run deploy:pi` targets only the Pi.
Reuse those paths for routine publication. A healthy unchanged Pi release must
remain a no-op, preserving the previous-release rollback link. Static Mac edits
are visible on refresh; there is no background auto-deployer.

Keep pages as plain reference tools: normal headings, content first, no hero or
marketing copy. Add a directory entry and Source/History links for each guide.
No external runtime fonts, scripts or CDN dependencies. Use `browser_clean` for
UI checks. Do not transmit IR or operate vehicle equipment during testing.

Run `npm test` for Python behavior tests and JavaScript syntax checks. Mac service
tests use temporary state and mocked launchd boundaries, without installing a
job. Keep files under 800 lines and functions under 80 unless a reviewed reason
requires an explicit exception. Reuse existing helpers before adding any.

Whenever BTT, iTerm, zsh or harness mappings change, update the canonical keyboard
catalog in the same task and verify both the guide and CLI (`npm test`, plus
browser checks). Keep each `verified` date honest: it records the source check,
not a live exercise in every app. Publish no full scripts, personal expansion
payloads, secret URLs or network names. Source references use `~/`, repo-relative
paths or fixed public system paths such as `/Applications`; never external URLs
or absolute personal home paths. Privacy tests flag
URLs, IPs, private hostnames, email addresses and unusually long action text;
they are regression tripwires, not proof of privacy. Review all strings manually.
Literal `@` keys are valid. Native macOS built-ins are out of scope.
The JSON schema declares fields/statuses once; both readers validate its supported
keywords and enforce unique ids and conditions for conditional entries. `keys`
contains consecutive chord/sequence steps; `sources` names source-of-truth paths.
Use `+` between modifiers and keys (`Cmd+X`, `Cmd+-` for the literal minus key),
not modifier hyphens. Canonical rows sort case-insensitively by provider, scope
and key steps, with id as a stable tie-breaker; both readers retain that order.
The CLI accepts text search, `--all`, exact `--provider`/`--scope`, `--json`,
`--details`, `--notes` and `--catalog PATH`; it resolves default data beside itself,
not from the caller's cwd. Default text shows grouped keys/actions/statuses, a
conditional-requirements notice and result count. `--details` adds row conditions,
limitations and provenance; `--notes` prints all catalog caveats after the rows.
JSON always retains complete records and notes. The guide keeps all catalog notes
inside a native, initially collapsed Coverage and limitations disclosure.
Exit 0 includes an empty result; malformed or missing data exits 2 on stderr.
Search is a literal case-insensitive phrase; options may be interspersed with its
words. Both readers also search concatenated sequence steps (`cosnt` matches
`C`, `O`, `S`, `N`, `T`, `Space`) without exposing private expansion content.
Both readers reject Unicode control/format and line/paragraph separators;
a leading UTF-8 BOM in a JSON file is accepted.

The keyboard catalog covers 54 BTT mappings, one hidutil remap and 59 terminal
mappings (18 global iTerm, eight shared profile, 20 existing zsh, the live Copy
Mode menu shortcut and 12 installed editing mappings). The 12 `terminal-*` editing
rows are conditional on new/reloaded zsh sessions, emacs/vi insert mode and their
stated selection/input requirements. Existing shells need `source ~/.zshrc` or a
new shell to load the widgets and `keys` function. Authenticated iTerm apply and a
zero-change post-check verified the two owned keys across 14 profile/session maps;
no actual keystrokes or clipboard tests were performed. Copy uses the previously
unused `Cmd+Ctrl+C`; `Cmd+Shift+C` remains iTerm Copy Mode and ordinary `Cmd+C` is
unchanged. The Ctrl+A dispatcher consumes only already-pending input, with no added
lookahead delay or partial-Unicode timeout; KEYTIMEOUT is unchanged. Same-write
or already-pending Ctrl+A then Ctrl+K typeahead is indistinguishable from Cmd+X;
delayed Ctrl+K keeps its native action. Empty cuts preserve the clipboard; native
Ctrl+Space regions survive Ctrl+A while Shift-selection ends. Ctrl+Y and harness
kill/yank behavior are not guaranteed. Outside zsh, Cmd+X is not universally safe:
Vim normal-mode Ctrl+A increments a number. Source/configuration verification and
isolated fresh-login/PTY checks never prove a successful live shortcut.

Commit and push (`c/p`) is the default here: Jacob rates this repo low-risk, so
once a change is finished and tests pass, commit it to `main` and push without
asking. Deployment goes with it: after every push, run `npm run deploy` without
asking, and report its outcome. If the deploy check fails, stop and report rather
than forcing it. This still does not cover Pi hardware changes: GPIO setup,
`hardware_setup.py configure`, enabling transmission, or system config outside the
Visual Guides release (such as Mosquitto).

Keep substantive unfinished work in ignored `.agent/handoffs/`; remove completed
handoffs after promoting durable facts here. Commit extraction/setup separately
from behavioral changes. Never publish private operational context.

## Contracts

| Path | Caller | Owner |
| --- | --- | --- |
| `app.py` | `visual-guides.service`, local preview commands and retained Pi releases | `visual_guides_server.py`, `visual_guides_cli.py` |
| `python3 -m local_service` | npm service lifecycle commands and installed Mac plist | `local_service/__main__.py`, `local_service/control.py` |
| `deploy.py` | npm combined and Pi deployment commands | `deploy.py` |
| `hardware_setup.py` | Documented Pi owner commands | `hardware_setup.py` |
| `keyboard_reference.py` | Mac zsh keyboard-reference command and direct terminal use | `keyboard_reference.py`, `static/reference/keyboard-shortcuts.json`, `static/reference/keyboard-shortcuts.schema.json` |
