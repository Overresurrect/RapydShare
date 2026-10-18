# RapydShare Security Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Implement `docs/superpowers/specs/2026-10-18-security-fixes-design.md` (the "spec"). The spec is the authority: read the sections each task names. Exact values (limits, alphabets, headers, messages) come from the spec verbatim.

**Architecture:** small focused modules (`src/paths.py`, `src/access.py`, `src/middleware.py`, `src/uploads.py`, `src/zipstream.py`, `src/thumbs.py`), wired together by `src/server.py`. A session cookie, obtained with a 6-character access code, replaces HTTP Basic auth.

**Tech Stack:** Python 3.12, FastAPI 0.145, Starlette 1.8, uvicorn 0.54, Pillow, OpenCV, PyQt6 + qfluentwidgets, React 19 + Vite 7 + Tailwind 3, pytest + TestClient (httpx2).

**Spec:** `docs/superpowers/specs/2026-10-18-security-fixes-design.md`

## Global Constraints

- Work in this worktree on branch `worktree-security-fixes` (based on `origin/main` `5dc9f71`). Commit locally; never push.
- Python: `/Users/aayushjamuar/Desktop/RapydShare/venv/bin/python`. Run the tests from the worktree root with `<python> -m pytest -q`.
- TDD: write the failing tests first, then the code. The full suite must pass before each commit.
- Windows and macOS are both supported; CI runs the tests on both. Use `pytest.mark.skipif` for platform-only tests.
- No new runtime dependencies.
- Tests never contact other hosts. A real socket may only bind `127.0.0.1`.
- Error responses never include file-system paths.
- Keep the existing code style (short functions, sparse comments).

## Shared names (every task uses these exact names)

- `src/paths.py`:
  - `path_text_is_safe(path: str) -> bool`
  - `resolve_in_root(path: str) -> Path` (raises `HTTPException`)
  - `is_hidden_name(name: str) -> bool`
  - `is_hidden(path: Path) -> bool`
  - `resolves_inside(path: Path, root: Path) -> bool`
  - `refuse_share_folder(folder: str) -> str | None`
- `src/access.py`:
  - constants `CODE_ALPHABET`, `CODE_LENGTH`, `SESSION_COOKIE = "rs_session"`
  - `new_code()`, `normalize_code(text) -> str | None`, `format_code(code) -> str`, `wait_after(failures) -> int`
  - `TooManyTries(retry_after: int)`
  - class `AccessControl` with module singleton `access`, methods:
    - `start(require_code: bool) -> str | None`
    - `stop()`
    - `.require_code`, `.code`
    - `try_code(client_ip, text) -> str | None` (raises `TooManyTries`)
    - `is_valid(token) -> bool`
    - `end_session(token)`
- `src/server.py`:
  - dependency `require_session(request)`
  - routes:
    - `GET /{code}` (a custom path convertor that only matches code-shaped segments)
    - `POST /api/login`, JSON `{"code": "..."}`: 204, or 401 `{"detail": "wrong_code"}`, or 429 with `Retry-After`
    - `POST /api/logout`
    - `GET /api/server_info`, returning `{"allow_upload": bool, "require_code": bool}`
  - 401 body for a missing session: `{"detail": "code_required"}`
- **Upload wire contract:**
  - `POST /api/upload`
  - raw file bytes as the body
  - headers `X-File-Name: encodeURIComponent(name)`, `Content-Type: application/octet-stream`, `Content-Length`
- Lifecycle (in `src/server.py`):
  - `parse_port(text) -> int` (raises `ValueError`)
  - `open_listen_socket(port, host="0.0.0.0") -> socket.socket`
  - `start_server(sock) -> threading.Thread`
  - `server_started() -> bool`
  - `stop_server(timeout=3.0) -> bool`
  - `open_cache_dir() -> Path`, `close_cache_dir()`
- Tests: the `TestClient` base URL is `http://127.0.0.1:8000` (from Task 6 on). The conftest `share` fixture calls `access.start(require_code=False)`; fixture `code_on` calls `access.start(require_code=True)` and returns the code.

---

### Task 1: Path checks before any file-system call

**Findings:** H2, L14, I2. **Spec:** §3 Path handling; §2 "Fail closed".
**Files:** create `src/paths.py`; modify `src/server.py` (`resolve_in_root` moves out); tests `tests/test_path_text.py` (new), `tests/test_paths.py` (extend).
**Produces:** `path_text_is_safe`, `resolve_in_root` (503 when no folder is configured; 403 for unsafe text or an escape; generic 404 for OS errors and alias forms).
**Acceptance:**
- every rejected form listed in spec §3 is refused by the text check
- a test proves an unsafe path is refused without calling `Path.resolve`
- 503 when there's no folder
- odd inputs never produce a 500
- the Windows alias test (win32 only) and the named-fork test (darwin only) pass
- all existing path tests still pass

### Task 2: Hidden and system files are never served

**Findings:** H1 (hidden files), L1 (listing part). **Spec:** §2 "Hidden and system files", §3 last bullet.
**Files:** `src/paths.py`, `src/server.py` (`list_files`); test `tests/test_hidden.py` (new); move the `link_out` fixture into `tests/conftest.py`.
**Consumes:** Task 1. **Produces:** `is_hidden_name`, `is_hidden`, `resolves_inside`. `resolve_in_root` returns 404 when any *resolved* component below the root is hidden.
**Acceptance:**
- dot-files, deny-listed names (any case), and the OS hidden flag (darwin `UF_HIDDEN`; win32 hidden/system attributes) are all left out of the listing and return 404 on every file endpoint
- a symlink pointing out of the share is left out of the listing

### Task 3: Access code core

**Findings:** M2, L6 (groundwork). **Spec:** §1 "The code", "Wrong guesses", "Signing out".
**Files:** create `src/access.py`; test `tests/test_access_core.py`.
**Produces:** everything under `src/access.py` in Shared names. Thread-safe (`threading.Lock`). An injectable clock for the tests.
**Acceptance:**
- code shape and alphabet are correct
- normalisation ignores case, spaces and dashes, and rejects wrong lengths and characters
- `format_code("K7M2X9") == "K7M 2X9"`
- `wait_after` matches the spec's backoff (5 free tries; then the wait doubles from 2 s up to 300 s)
- attempts during a wait aren't counted
- other IPs are unaffected
- a success resets that IP
- `stop()` ends sessions; `end_session` works

### Task 4: Replace Basic auth with the access code

**Findings:** H1, M2, L6, L8 (sessions). **Spec:** §1 (the address, bare address, the code-entry API side, signing out).
**Files:** `src/server.py`, `src/config.py` (drop `USE_AUTH`/`USERNAME`/`PASSWORD`, add `REQUIRE_CODE = True`), `src/gui.py` (minimal shim only: start and stop the access code and put the code in the link; Task 10 does the real UI), `tests/conftest.py`; replace `tests/test_auth.py` with `tests/test_access.py`.
**Consumes:** Task 3. **Produces:** `require_session`, the routes and the cookie as given in Shared names and spec §1.
**Notes:**
- The code route is registered before the static mount and must not shadow static files.
- `/api/login` refuses bodies without a `Content-Length` (411) or over 1024 bytes (413) before parsing.
- Wrong codes in the URL count toward the limit.
**Acceptance:**
- every `/api/*` route except login needs a session
- the code URL sets the cookie (`HttpOnly`, `SameSite=Strict`) and 303s to `/`, after which API calls succeed
- the URL code ignores case and dash
- the login API behaves as specified, including 429 with `Retry-After`
- logout and stop end access
- `QT_QPA_PLATFORM=offscreen <python> -c "import src.gui"` still works

### Task 5: Upload gate, safe writing and names

**Findings:** M3, L2, L5, L7. **Spec:** §4 Uploads (all of it).
**Files:** create `src/uploads.py` (move `sanitize_filename`, the reserved names and the naming helper out of `server.py`); `src/server.py` (`upload_file`); `build.py` (`LSFileQuarantineEnabled`); rewrite `tests/test_upload.py`; extend `tests/test_filenames.py`.
**Consumes:** `require_session` (Task 4), `is_hidden` (Task 2). **Produces:** the upload wire contract from Shared names.
**Acceptance:**
- the upload route has no body parameters (`route.body_field is None`)
- 401, 403, 411, 413 and 507 all happen without writing anything, neither to the upload folder nor to a temp folder
- concurrent same-name uploads never overwrite each other
- a failed or aborted upload leaves no `.part` file and no placeholder
- error bodies contain no paths
- non-ASCII and emoji names round-trip
- all of spec §4's name rules are covered
- quarantine (darwin) and `Zone.Identifier` (win32) tests pass
- the six behaviours of the old upload tests are kept

### Task 6: Browser protections

**Findings:** M4, M6, L8 (no-store), I1. **Spec:** §5 (all of it).
**Files:** create `src/middleware.py`; `src/server.py` (`view_media`, `FastAPI(...)` docs off); `tests/conftest.py` (`base_url`); test `tests/test_browser.py`.
**Acceptance:**
- the Host allowlist accepts IP literals with ports, `[::1]`, `localhost` and the machine's own `<name>.local` in any case, and returns 400 for anything else
- a cross-origin non-GET request gets 403
- the security headers are present
- frame rules: `SAMEORIGIN` / `'self'` on `/api/view`, `DENY` / `'none'` elsewhere
- `no-store` on `/api/*`
- HTML, SVG and XML come back as `text/plain` with the sandbox CSP; PDF comes back without a sandbox CSP
- `/docs`, `/redoc` and `/openapi.json` return 404
- a video `Range` request still gets 206

### Task 7: Streaming folder ZIPs

**Findings:** M5, L1. **Spec:** §6.
**Files:** create `src/zipstream.py`; `src/server.py` (`download_folder`); rewrite `tests/test_download_folder.py`, keeping its three behaviours: concurrent downloads each get their own folder, nothing is left in the cache folder, and a failure leaves nothing on disk.
**Consumes:** `is_hidden`, `resolves_inside` (Task 2).
**Notes:**
- An unreadable file is skipped, and the ZIP still completes.
- The concurrency slot is released exactly once, even when a stream is abandoned or never started.
- `Content-Disposition` matches Starlette's `FileResponse` format (`filename="docs.zip"`).
**Acceptance:**
- symlinks pointing out of the share, hidden files and the app's cache folder are excluded
- links that stay inside the share are included
- a third concurrent ZIP gets 503 with `Retry-After: 5`
- an abandoned stream frees its slot
- a large file streams in several chunks

### Task 8: Thumbnails

**Findings:** L3, L10. **Spec:** §7.
**Files:** create `src/thumbs.py` (no Qt import); `src/server.py` (`get_thumb`, plus `open_cache_dir` / `close_cache_dir`); `src/config.py` (remove the import-time `rmtree`; `THUMB_CACHE_DIR` starts as `None`); `src/utils.py` (remove `generate_thumbnail`); test `tests/test_thumbs.py`.
**Acceptance:**
- images over the pixel cap are refused *before* decoding
- formats outside the allowlist get no thumbnail
- the size caps are enforced
- a changed file gets a new thumbnail
- a deleted file returns 404 even when cached
- failures are recorded and not retried
- `open_cache_dir` and `close_cache_dir` create and remove the per-run folder

### Task 9: Stop really stops, honest start, no stalls

**Findings:** L4, L9 (server side), L11. **Spec:** §8.
**Files:** `src/server.py`, `src/gui.py` (call sites only: switch to the new start/stop functions), `main.py` (`aboutToQuit` → `stop_server`); test `tests/test_lifecycle.py`.
**Produces:** the lifecycle functions in Shared names. `stop_server` also calls `access.stop()` and `close_cache_dir()`.
**Acceptance:**
- `parse_port` accepts 1–65535 and rejects everything else
- binding a port that's in use raises `OSError`
- a real server on `127.0.0.1:0` starts and serves, and `stop_server` returns within about 3 s even while a slow download is in progress
- the file endpoints are plain `def`, not async
- on darwin, the raised file limit is applied

### Task 10: Desktop app

**Findings:** H1 (folder), M1 (note), L9 (UI side), L4 (window close). **Spec:** §1 "GUI", §2 "Picking the folder", §8.
**Files:** `src/gui.py`, `src/paths.py` (`refuse_share_folder`); tests `tests/test_folders.py` and `tests/test_gui_smoke.py` (offscreen; skip if Qt can't start).
**Consumes:** Tasks 3, 4 and 9.
**Acceptance:**
- `refuse_share_folder` refuses home, the system root and OS folders, and allows a subfolder
- the window starts with an empty folder box when nothing is remembered
- the folder choice is remembered via `QSettings`
- the "Require access code" switch is on by default; turning it off shows a warning
- no username or password fields
- the code is shown as `XXX XXX` with a Copy link button
- the "Not encrypted" note is visible
- start shows the address only after `server_started()`; a failure is shown and the app stays stopped
- closing the window stops the server

### Task 11: Web client

**Findings:** M6 (iframe), L8 (Disconnect); the client side of Tasks 4 and 5. **Spec:** §1 "Bare address", "The code-entry form", "Signing out"; §5 "Frontend".
**Files:** `frontend/src/App.tsx`, `frontend/src/components/CodeEntry.tsx` (new), `frontend/src/components/PreviewModal.tsx`, `frontend/src/types.ts` as needed.
**Consumes:** the routes and upload wire contract from Shared names.
**Acceptance:**
- `npm run lint` and `npm run build` pass
- the code form behaves exactly as spec §1 describes: boxes, auto-advance, backspace, arrows, paste, auto-submit, shake, countdown, mobile hints, 320 px fit and screen-reader labels
- any 401 shows the form
- Disconnect ends the session
- uploads use the new wire contract
- the text preview iframe is sandboxed; the PDF iframe isn't

### Task 12: Dependencies, CI and README

**Findings:** L12, L13. **Spec:** §9.
**Files:** `requirements.txt` (remove `tinyaes`), `requirements.lock` (new, generated with hashes, covering both platforms), `README.md`, `.github/workflows/tests.yml`, `frontend/package.json`, `frontend/package-lock.json`.
**Acceptance:**
- the lock installs with `--require-hashes`
- `npm audit fix` (no `--force`) is applied and lint/build still pass
- actions are pinned to commit SHAs with the tag as a comment
- `permissions: contents: read` is set
- a non-blocking `npm audit --omit=dev` step is added
- the README drops "secure" and documents the access code, the no-encryption limit, hidden files and uploads being off by default, plus the locked build install
