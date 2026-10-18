# RapydShare security fixes: design

**Date:** 2026-10-18
**Source:** the security audit in `.claude/security-audit-2026-10-18.md` (local and gitignored; finding IDs H1–L14 below refer to it).
**Scope:** every High, Medium and Low finding. Info items are out of scope, except the two that come free with code being changed anyway (see "My calls").

## Intent

RapydShare is for quick, one-off transfers between devices on the same Wi-Fi, usually a home network:

- iPhone to PC
- Mac to PC
- a friend in the same room

You start the server, the other device opens the address or scans the QR code, files move, you stop. The audit found that the defaults expose far more than the user means to share, to anyone on the network, and that several endpoints can be abused. The goal is to make the safe setup the default **without making the scan-and-go flow any harder**.

## Who it's for

- People who aren't technical. They pick a folder, press Start, and expect the other device to just open the address.
- The other end is often a phone scanning the QR code. Sometimes it's a computer where someone types the address.
- iPhone to PC is an upload, so uploads are a core flow, not an extra.
- The network is usually home Wi-Fi, sometimes a shared one (dorm, office, café).

## Goals

1. Nobody on the Wi-Fi can get in without the access code, and the code is on by default.
2. Scanning the QR code, pasting the link or typing the address remains a single step with nothing extra to type.
3. Only the folder the user picked is ever reachable, minus hidden and system files.
4. No endpoint can be used to fill the host's disk, crash it, or make it connect elsewhere.
5. Files from the share can't run script in the visitor's browser.
6. Stop actually stops.
7. Every fix has a regression test where it can be tested without a GUI.

## Non-goals

- HTTPS. A self-signed certificate warning on a phone breaks scan-and-go. The app says plainly that the connection isn't encrypted instead.
- The friendly `rapydshare.local` name and nearby discovery. They are the next project.
- User accounts, or different permissions for different visitors.
- Code signing (unsigned distribution is an accepted choice).

## Anti-goals (a failure even if it technically works)

- A phone that scans the QR code lands on a login screen or a certificate warning.
- The user has to read or type a long random string.
- A fix silently breaks today's flows: browsing, previews, downloads, folder ZIPs, uploads with progress.
- Windows-only protections that are never tested on Windows. CI already runs the server tests on `windows-latest` and `macos-latest`; new tests must run there too.

## Constraints

- Backend: FastAPI 0.145 / Starlette 1.8 / uvicorn 0.54 on Python 3.12.
- GUI: PyQt6 plus qfluentwidgets, a fixed 680×740 window.
- Frontend: React 19 / Vite 7 / Tailwind 3.
- Platforms: Windows and macOS (Apple Silicon). Linux isn't supported.
- Start from `origin/main` (`5dc9f71`). It already has PR #3, which gives folder ZIPs unique names and deletes them after sending.
- No new runtime dependencies unless clearly necessary.

---

## Decided by Aayush

- **Access code in the address** replaces username and password. Scanning, pasting or typing the address gets you in, and a bare address asks for the code.
- **No HTTPS for now.** The app shows a clear "not encrypted" note.
- **The person sharing always picks the folder.** No pre-filled home folder.
- **Security first.** The `.local` name and nearby discovery come later.

---

## Design

### 1. Getting in: the access code (H1, M2, L6, L8)

**The code.**

- 6 characters, uppercase letters and digits, drawn from `23456789ABCDEFGHJKMNPQRSTUVWXYZ`. That's 31 symbols with look-alikes left out: no `0`, `O`, `1`, `I` or `L`. About 8.9×10⁸ combinations.
- Displayed as two groups of three, e.g. `K7M 2X9`.
- Generated with `secrets` each time Start is pressed. Pressing Stop throws it away.

**The address.**

- The GUI shows `http://<ip>:<port>/<CODE>` (e.g. `/K7M2X9`), matched case-insensitively. The QR code and the clipboard copy are this same address.
- The code route must not shadow static assets. It only matches a single path segment that normalises to a valid 6-character code.
- Opening it gives the browser a session cookie and redirects to `/`, so the code leaves the address bar.
- Cookie settings: random 32-byte token, `HttpOnly`, `SameSite=Strict`, `Path=/`, no `Max-Age` (it ends when the browser closes).
- Sessions are held in server memory and cleared on Stop.

**Bare address.**

- `/` loads the web client as today. The static bundle holds no secrets and stays public.
- When the API says the visitor isn't signed in, the client shows one screen: "Enter the code shown in RapydShare", with an OTP-style entry form.
- A correct code starts a session the same way the code URL does.

**The code-entry form** (decided by Aayush: alphanumeric, filled like a one-time passcode):

- 6 single-character boxes in two groups of three, matching how the app displays the code. The first box is focused on load.
- Typing a valid character fills the box and moves to the next. Lowercase becomes uppercase, and characters outside the code alphabet are ignored.
- Backspace in an empty box moves back and clears the previous box. Left and right arrows move between boxes.
- Pasting into any box fills all six from the pasted text, ignoring spaces, dashes and case.
- Mobile keyboard hints: `autocapitalize="characters"`, `autocorrect="off"`, `spellcheck={false}`, `autocomplete="one-time-code"` (on the first box, or one hidden input the boxes mirror; builder's call).
- Filling the last box submits automatically. There's no submit button to press, though Enter also submits.
- A wrong code makes the boxes shake, clears them and focuses the first box.
- On `429`, the form shows "Too many tries — try again in N s", counts down from `Retry-After`, and re-enables itself.
- Boxes are large enough to tap on a phone; the six of them must fit in a 320 px-wide screen. Each box is labelled for screen readers ("Character 1 of 6", and so on).

**Wrong guesses.**

- Failed codes are counted per client IP, whether typed in the box or tried in the address.
- After 5 failures the server answers `429` with `Retry-After`. The wait doubles with each further failure, up to 5 minutes.
- A success resets that IP's count.
- Counts are in memory and cleared on Stop.

**Every `/api/*` route** requires a valid session when the code is required. This replaces HTTP Basic auth entirely.

**Signing out.** The web client gets a small "Disconnect" action that ends that browser's session. Stop ends all sessions.

**GUI.**

- The Username and Password fields go away.
- A "Require access code" switch is added, on by default. Turning it off shows a warning: anyone on this Wi-Fi can open your shared folder.
- While running, the code is shown large and readable next to the QR code, with a "Copy link" button.
- A one-line note: "Not encrypted. Use on networks you trust."

### 2. Shared folder and hidden files (H1)

**Picking the folder.**

- The folder box starts empty ("Choose a folder to share…"), and Start refuses to run until one is picked.
- The app remembers the last folder picked (Qt `QSettings`) and pre-fills it next time.
- Start refuses, with a plain message, these choices:
  - the user's home folder itself
  - the system drive root (`C:\`, `/`)
  - OS folders (Windows directory, Program Files, `/System`, `/Library`, `/Applications`, `/usr`, `/bin`, `/etc`, `/private`, `/var`)
- Subfolders of home, and roots of *external* drives, are allowed.
- The check lives in a plain, Qt-free function so it can be unit-tested.

**Hidden and system files are never served.**

- Any path component counts as hidden if it:
  - starts with `.`
  - is on a small deny-list (`desktop.ini`, `Thumbs.db`, `$RECYCLE.BIN`, `System Volume Information`)
  - has the OS hidden flag set: `UF_HIDDEN` on macOS, which also covers `~/Library`; `FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM` on Windows
- Enforce it in three places:
  - in path resolution: such paths return 404, as if they don't exist
  - in the listing
  - in folder ZIPs
- No opt-in toggle in this round.

**Fail closed:** if no shared folder is configured, every file endpoint returns `503`.

### 3. Path handling (H2, L14, plus I2)

Before **any** file-system call, `resolve_in_root` rejects the request path *as text*:

- it contains a NUL or `:`
- `PureWindowsPath(path)` has a drive or root (this covers UNC `\\host\share`, `//host/share`, `C:\x`, `C:x`, `\\?\…`, `\\.\…`)
- it starts with `/` or `\`

Parse with `PureWindowsPath` on every platform, so macOS CI catches the Windows forms.

Then:

- resolve and keep the `is_relative_to(root)` check as defense in depth
- on Windows, refuse components ending in `.` or a space, and `..namedfork` on macOS
- `OSError`, `ValueError` and `RuntimeError` from resolution or stat map to a generic 400 or 404 with no path in the message
- symlinks that resolve inside the share keep working; ones that point outside are refused everywhere, the listing and ZIPs included (see 6)

### 4. Uploads (M3, L2, L5, L7)

**Nothing touches disk before the checks.**

- `/api/upload` must reject the request before any of the body is read when:
  - the session is invalid (401)
  - uploads are off (403)
  - `Content-Length` is missing or over the limit (411/413)
- Then it streams the body itself straight into the upload folder. Starlette's spooling to the system temp folder is not used.
- Handle one file per request, as the client already does.

**Limits** (constants, not GUI settings):

- at most 20 GB per file
- refuse, or stop and clean up, if writing would leave less than 1 GB free on the destination disk

**Writing.**

- Write to a hidden `.<name>.part` in the upload folder; hidden files are never served, so partial uploads can't be downloaded.
- Then move it into place with an exclusive create (`O_EXCL` semantics), stepping to `name (1).ext`, `name (2).ext` and so on if the name exists.
- Clean up the part file on any failure.
- Errors returned to the client are generic, with details logged locally.

**File names** (`sanitize_filename`), on top of today's rules:

- NFC-normalize
- replace Unicode categories `Cc` `Cf` `Cs` `Co` `Cn` `Zl` `Zp` (bidi overrides, zero-width characters and the like) with `_`
- strip any mix of leading and trailing spaces and dots
- reserved names, matched on `stem.rstrip().upper()`, are now `CON PRN AUX NUL CONIN$ CONOUT$ COM0–9 COM¹²³ LPT0–9 LPT¹²³`
- cap at 200 bytes of UTF-8, keeping the extension
- risky Windows types get `.txt` appended so they can't act on their own: `.url .lnk .scf .library-ms .searchConnector-ms`, and a file named `desktop.ini`

**Marked as downloaded.**

- macOS: add `LSFileQuarantineEnabled = True` to the Info.plist that `build.py` writes, so the packaged app quarantines files it creates. When running from source, also set `com.apple.quarantine` on each saved upload, best effort, via `ctypes`.
- Windows: write a `:Zone.Identifier` stream containing `[ZoneTransfer]\r\nZoneId=3` on each saved upload, best effort.

### 5. Browser protections (M4, M6, L8, plus I1)

**A middleware for all responses:**

- Allowed `Host` values: IP literals (v4 or bracketed v6), `localhost`, and the machine's own `<hostname>.local`. Anything else gets a 400. This is what stops DNS rebinding.
- On non-GET/HEAD requests, an `Origin` header that is present and doesn't match the request's own scheme, host and port gets a 403.
- Headers on every response: `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, and frame protection (merged with any per-route CSP):
  - `/api/view`: `X-Frame-Options: SAMEORIGIN` and `frame-ancestors 'self'`, because the web client shows previews in its own iframes
  - every other response: `X-Frame-Options: DENY` and `frame-ancestors 'none'`
- `Cache-Control: no-store` on every `/api/*` response.

**`/api/view`:**

- Only a safe list renders inline: images except SVG, video, audio, PDF and plain text.
- Everything else, including HTML, XHTML, SVG and XML, is served as `text/plain; charset=utf-8`.
- Every non-PDF response gets `Content-Security-Policy: sandbox; default-src 'none'; img-src 'self'; media-src 'self'; style-src 'unsafe-inline'`.
- PDF gets no `sandbox` CSP (the frame protection above still applies). Browsers' built-in PDF viewers, Chrome's in particular, refuse to render inside a sandbox. PDFs stay safe through `nosniff` and the browser's own PDF viewer isolation.

**Frontend:** the text-preview `<iframe>` gets `sandbox=""`. The PDF `<iframe>` stays unsandboxed, for the reason above. Check that PDF and text previews still render in Safari, Chrome and Firefox.

**Docs pages off:** `FastAPI(docs_url=None, redoc_url=None, openapi_url=None)`.

### 6. Folder downloads (M5, L1)

- Replace `shutil.make_archive` with our own walk: `os.walk(followlinks=False)`, including a file only if `Path(p).resolve().is_relative_to(root)`, it's a regular file and it isn't hidden.
- Never descend into the app's own cache or temp folder.
- Stream the archive to the client (`zipfile` writing into a `StreamingResponse`), so no full copy lands on disk.
- If streaming proves impractical with Starlette, keep PR #3's temp-file approach and add the walk rules above plus a free-space check.
- At most 2 folder ZIPs at once; a third request gets `503` with `Retry-After`.
- ZIP work runs in its own small pool, separate from thumbnails. If the client goes away, stop zipping.
- The listing uses the same symlink rule: links pointing outside the share are left out.

### 7. Thumbnails (L3, L10)

**Limits.**

- Only thumbnail JPEG, PNG, GIF, WebP and BMP images, plus video.
- Skip files larger than 200 MB for images and 4 GB for video.
- After `Image.open`, refuse if width × height exceeds 50 million pixels, before any decoding.
- Use `draft()` for JPEG.

**Cache.**

- Check that the file exists and is a regular file before using the cache.
- Key the cache on `st_dev`, `st_ino`, `st_mtime_ns` and `st_size` rather than the path string.
- Record failures so they aren't retried.
- Write the cache file atomically.

**Cache folder.**

- Create a private folder each run with `tempfile.mkdtemp(prefix="RapydShare_")` when the server starts.
- Delete it on Stop and on exit.
- Remove the import-time `rmtree` in `src/config.py`.

### 8. Server lifecycle and robustness (L4, L9, L11)

**Stop actually stops.**

- Pass `timeout_graceful_shutdown=1` to uvicorn.
- Stop and join the server thread on the Stop button and on window close (`closeEvent` and `aboutToQuit`).
- The GUI shows "Offline" only after the thread has ended.

**Start tells the truth.**

- Port must be in the range 1–65535.
- Bind the socket in the GUI thread first (`socket.create_server`) and pass it to uvicorn.
- On failure, show the error and stay stopped.
- Show the address, QR code and code only once uvicorn reports it has started.

**No stalls.**

- File-system work in handlers runs off the event loop, as plain `def` handlers or `run_in_threadpool`.
- On macOS, raise the soft `RLIMIT_NOFILE` toward 10240 at startup.
- Use the closest available uvicorn setting to drop idle connections that never send a request; document the limit if uvicorn has none.

### 9. Dependencies, CI and README (L12, L13)

**Dependencies.**

- Add a hash-locked `requirements.lock` for release builds, generated with `uv pip compile --generate-hashes`.
- Document `pip install --require-hashes -r requirements.lock` before `python build.py`.
- Remove `tinyaes`.
- Run `npm audit fix` (without `--force`) in `frontend/`.

**CI.**

- Pin each action to a commit SHA, with the tag as a comment.
- Add `permissions: contents: read`.
- Add a non-blocking `npm audit --omit=dev` step.

**README.**

- Drop "secure" from the tagline.
- Describe the access code, the "not encrypted" limit, that hidden files are never shared, and that uploads are off until turned on.
- Keep the change small, since the unmerged `readme-and-author-name` branch rewrites the README.

---

## Testing

Server-side changes get pytest coverage in `tests/` and run on the existing Windows and macOS CI. Tests check behaviour through `TestClient` or pure functions, never real network calls. At least:

- Access code:
  - the code URL sets a session and redirects
  - a wrong code gets 401
  - repeated wrong codes get 429 with `Retry-After`
  - every `/api/*` route needs a session
  - turning the code off opens the routes
  - Stop clears sessions
- Paths:
  - `//host/x`, `\\host\x`, `C:x`, `C:\x`, NUL and `a:b` are refused by the text validator before any filesystem call (unit test)
  - existing traversal tests still pass
- Hidden files: dot-files, deny-listed names and flagged files are absent from the listing, 404 on direct access and missing from ZIPs
- Folder check: home, system root and OS folders are refused; a subfolder is allowed
- Uploads:
  - unauthenticated, disabled and over-limit requests are rejected without writing anything to disk
  - same-name uploads never overwrite each other
  - partial files are removed on failure
  - the new name rules work
  - error bodies contain no paths
- Browser:
  - a foreign `Host` gets 400
  - a cross-origin POST gets 403
  - security headers are present
  - `/api/view` of `.html` and `.svg` comes back as `text/plain` with a sandbox CSP
  - `/docs` returns 404
- ZIP: symlinks pointing out of the share and hidden files are excluded; a third concurrent ZIP gets 503
- Thumbnails: an oversized image is refused before decoding; the cache key changes when the file changes; a deleted file gets 404

GUI and frontend changes are checked by `npm run lint` / `npm run build` and a manual run. Put GUI logic worth testing (folder check, port check, code generation and normalisation) in Qt-free helpers with unit tests.

## Left to the builder

- Module layout, for example an `access.py` for codes and sessions, and where the middleware lives.
- Exactly how the upload gate is implemented (ASGI middleware, raw `Request` streaming, or both), as long as the "nothing on disk before checks" test passes.
- Whether folder ZIPs stream or keep the temp-file fallback (see 6).
- Wording and layout of GUI messages, within the fixed window.
- The exact CSP strings, as long as previews still work and the tests pass.

## My calls (not explicitly decided by Aayush; flag any you disagree with)

- Code length of 6 (Aayush chose alphanumeric with an OTP-style form). Per-IP backoff after 5 misses, up to 5 minutes. No automatic code change after repeated wrong guesses: with about 900 million codes and per-IP backoff it isn't needed, and it would make the host re-share codes.
- A "Require access code" switch exists (on by default, with a warning when off) rather than the code being mandatory.
- The app remembers the last folder picked. Home, system root and OS folders are refused outright, not just warned about.
- Hidden and system files are never served, with no opt-in.
- Upload limits: 20 GB per file and 1 GB of free space kept.
- Risky Windows file types get `.txt` appended rather than being refused.
- A "Disconnect" action in the web client.
- Two Info items are included because they're one-liners in code already being changed: I1 (docs pages off) and I2 (no unhandled 500s on odd paths).
- Work goes on a new branch `security-fixes` from `origin/main`.
- PDF previews are left unsandboxed so they keep working; every other risky type is neutralised (from the design review).
- `/api/view` allows same-origin framing for the client's previews; everything else denies framing (from the design review).
