# RapydShare ⚡

Share files between your computer and any phone, tablet, or laptop on the same Wi-Fi. Pick a folder, click **Start Server**, and scan the QR code (or open the link) in a browser on the other device. There's nothing to install on the other device, and no accounts or cloud services involved.

[![Latest release](https://img.shields.io/github/v/release/Overresurrect/RapydShare)](https://github.com/Overresurrect/RapydShare/releases/latest)
[![License: MIT](https://img.shields.io/github/license/Overresurrect/RapydShare)](LICENSE)
![Platforms](https://img.shields.io/badge/platform-Windows%20%7C%20macOS-blue)

![RapydShare Screenshot](assets/Screenshot.jpg)\
*RapydShare desktop app*

![RapydShare Browser Screenshot](assets/Screenshot-Web.jpg)\
*RapydShare web client*

## 🚀 Features

**Desktop app (the computer sharing files)**

- Share a folder of your choice on a port you choose (8000 by default).
- An access code, on by default, so only people you give it to can get in. It changes every time you start sharing, and the QR code and link already contain it.
- Shows a QR code and copies the link to your clipboard as soon as the server starts.
- Won't share your whole home folder, the system drive, or system folders, and never shares hidden or system files.
- Optional uploads: pick a folder where files sent from other devices are saved.
- Stop really stops: transfers in progress end within about a second.
- Dark, Fluent-style interface built with PyQt6 and QFluentWidgets.

**Web client (the other devices)**

- Works in any modern browser, on mobile or desktop.
- Scan the QR code and you're in. If you type the address by hand, enter the access code in six boxes, like a one-time passcode.
- Browse folders in a grid or list view, and search the current folder.
- Thumbnails for images and videos.
- Previews for images, videos, PDFs, and text files.
- Download single files, or whole folders as a ZIP.
- Upload several files at once, by picking them or dragging them onto the page, with a progress bar for each one and a cancel button.
- Light and dark themes. The theme follows your system until you pick one, and the page remembers your theme and view choices.

## 📦 Installation

Download the latest version from the [Releases page](https://github.com/Overresurrect/RapydShare/releases/latest).

### Windows

1. Download `RapydShare.exe` and run it. Nothing gets installed; it's a single portable file.
2. The app isn't code-signed, so Windows SmartScreen may warn you the first time. Click **More info**, then **Run anyway**.
3. When Windows Defender Firewall asks the first time you start the server, allow access on **Private networks**. Other devices can't connect otherwise.

### macOS

Requires a Mac with Apple Silicon (M1 or newer) running macOS 14 Sonoma or later.

1. Download `RapydShare-mac-arm64.dmg`.
2. Open it and drag **RapydShare** into your **Applications** folder.
3. Open RapydShare. The app isn't signed with an Apple Developer certificate, so macOS blocks it the first time:
   1. Click **Done** on the warning.
   2. Open **System Settings → Privacy & Security**, scroll down, and click **Open Anyway** next to the RapydShare message.
   3. Confirm with **Open Anyway**. You only need to do this once.

   If you're comfortable with the terminal, `xattr -dr com.apple.quarantine /Applications/RapydShare.app` does the same thing.
4. If macOS asks whether RapydShare can accept incoming network connections or find devices on your local network, click **Allow**. Other devices can't connect otherwise.

### Other platforms

There's no build for Intel Macs or Linux yet. You can still run RapydShare from source on them (see [Development](#-development)), though that isn't tested.

## 📲 How to Use

1. **Choose a shared folder.** RapydShare remembers the last folder you picked. It won't share your whole home folder (or a folder that contains it), the system drive, system folders, or hidden folders. Pick a folder inside them instead. iCloud Drive, Dropbox, OneDrive, Google Drive, and external drives all work.
2. **(Optional) Change the port** if 8000 is already in use.
3. **Keep Require access code on.** Each time you start the server, RapydShare makes a new 6-character code, like `K7M 2X9`. Turn it off only on a network where you trust everyone; the app warns you if you do.
4. **(Optional) Turn on Allow Uploads** and choose a folder to receive files. Uploads always go into this folder, whatever folder the sender is browsing. They only show up in the web client if this folder is inside the shared folder, and the app warns you if it isn't.
5. Click **Start Server**.
6. On the other device, scan the QR code or open the link the app shows, for example `http://192.168.1.20:8000/K7M2X9`. Both already contain the access code. If you type just the address (`http://192.168.1.20:8000`), the page asks for the code shown in the app.

Click **Stop Server** when you're done. It ends every transfer and everyone's access, and the next start gets a new code. The settings are locked while the server is running.

Some things to know:

- Uploaded files never overwrite each other. If a file with the same name already exists, the new one is saved as `name (1).ext`, `name (2).ext`, and so on.
- Each upload can be up to 20 GB, and RapydShare always leaves at least 1 GB free on the disk it saves to.
- Received files are marked as downloaded from the internet, so macOS and Windows check them before you open them. Risky Windows file types, such as `.lnk` and `.url`, get `.txt` added to their name.
- Folder downloads start straight away, and up to two can run at once.
- Hidden files (names starting with a dot) and system files are never listed, downloaded, or included in folder downloads.

## 🔒 Security

RapydShare is meant for networks you trust, like your home Wi-Fi.

- **Connections are not encrypted.** RapydShare uses plain HTTP, not HTTPS, so anyone who can watch the network traffic can read what's transferred, including the access code.
- **The access code is on by default** (**Require access code**). Without it, anyone who can reach your computer on that port can browse and download from the shared folder, so the app warns you when it's off.
- Wrong codes are slowed down, so the code can't realistically be guessed. Stopping the server ends everyone's access, and the next start makes a new code.
- RapydShare refuses to share your home folder, the system drive, or system folders, and never shares hidden or system files.
- Uploads are off by default. Turn them on only while you need them.
- Stop the server when you're finished sharing.

## 🩺 Troubleshooting

**The link doesn't load on my phone.**

- Make sure both devices are on the same network. Guest Wi-Fi networks often block devices from reaching each other.
- Check that you allowed RapydShare through the firewall (Windows) or allowed local network access (macOS).
- If you're on a VPN, the link may show the VPN's address instead of your Wi-Fi address. Turn the VPN off, or use your computer's Wi-Fi IP address with the same port.
- Another app may already be using the port. RapydShare tells you when it can't start; change the port and start it again.

**The page asks for a code.** Enter the code shown in the RapydShare app, or scan the QR code instead. Codes from an earlier session stop working once the server is stopped.

**RapydShare won't share the folder I picked.** It refuses your whole home folder, the system drive, system folders, and hidden folders. Pick a folder inside them, such as Documents or a new folder for sharing.

**Uploads don't appear in the file list.** The upload folder is outside the shared folder. Pick an upload folder inside the shared folder.

**macOS says the app can't be opened, or is damaged.** Follow the **Open Anyway** steps in [Installation](#macos).

## 🛠️ Tech Stack

| Part | Built with |
| --- | --- |
| Desktop GUI | PyQt6, PyQt6-Fluent-Widgets |
| Server | Python, FastAPI, Uvicorn |
| Thumbnails | Pillow, OpenCV |
| Web client | React 19, TypeScript, Tailwind CSS, Vite |
| Packaging | PyInstaller |

## 💻 Development

### Prerequisites

- Python 3.12 or newer (release builds from `requirements.lock` use Python 3.12, which is what the lock is resolved for)
- Node.js 20.19+ or 22.12+ (required by Vite 7), with npm

### Setup

```bash
git clone https://github.com/Overresurrect/RapydShare.git
cd RapydShare

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements-dev.txt

cd frontend
npm install
cd ..
```

### Run the app

The desktop app serves the built web client from `frontend/dist`, so build it before launching. Run `main.py` from the repository root, because the app finds `frontend/dist` and `assets` relative to the current folder.

```bash
cd frontend
npm run build
cd ..
python main.py
```

### Run the tests

```bash
pytest
cd frontend
npm run lint
npm test
```

CI runs the server tests on Windows and macOS, and lints, tests, and builds the web client.

### Work on the web client

For live reloading, start the server from the desktop app on port **8000**, then run the Vite dev server in a second terminal:

```bash
cd frontend
npm run dev
```

Open `http://localhost:5173` and enter the access code shown in the app. Vite forwards `/api` requests to `http://127.0.0.1:8000`.

### Project structure

```text
main.py              Entry point: starts the Qt app
src/gui.py           Desktop window: settings, access code, QR code, start/stop
src/server.py        FastAPI app: file API, web client hosting, server start/stop
src/access.py        Access codes, sessions, and the wrong-guess slowdown
src/paths.py         Path checks, hidden files, and which folders can be shared
src/middleware.py    Host and Origin checks, and security headers
src/uploads.py       Upload limits, safe file names, and writing uploads
src/zipstream.py     Streaming folder downloads
src/thumbs.py        Thumbnails and their cache
src/config.py        Settings shared by the GUI and server
src/utils.py         Local IP lookup and QR codes
frontend/            React web client
tests/               Server tests (pytest)
build.py             PyInstaller build for Windows and macOS
make_mac_icon.py     Generates the macOS icon
version_info.txt     App version and Windows file metadata
```

<details>
<summary>API endpoints</summary>

When **Require access code** is on, every `/api` endpoint except `/api/login` needs the session cookie that signing in with the code sets. File endpoints take a `path` relative to the shared folder.

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/<code>` | Signs in with the code from the QR code or link, then redirects to `/` |
| `POST` | `/api/login` | Signs in with `{ "code": "..." }` |
| `POST` | `/api/logout` | Ends this browser's session |
| `GET` | `/api/files?path=` | Lists a folder |
| `GET` | `/api/thumb?path=` | JPEG thumbnail of an image or video |
| `GET` | `/api/view?path=` | Serves a file inline for previews (HTML, SVG, and other active types as plain text) |
| `GET` | `/api/download?path=` | Downloads a file |
| `GET` | `/api/download_folder?path=` | Downloads a folder as a ZIP |
| `GET` | `/api/server_info` | Returns `{ "allow_upload": bool, "require_code": bool }` |
| `POST` | `/api/upload` | Uploads one file: the raw file as the body, with its name in an `X-File-Name` header |

</details>

### Build a release

Build on the platform you're targeting. PyInstaller can't cross-compile. Install the hash-locked dependencies first, in a clean environment:

```bash
pip install --require-hashes -r requirements.lock
cd frontend
npm ci
npm run build
cd ..
python build.py
```

The output lands in `dist/`:

- **Windows:** `RapydShare.exe`, a single-file app.
- **macOS:** `RapydShare.app` and `RapydShare-mac-arm64.dmg`, ready to upload to a release. The script ad-hoc signs the app and prints the minimum macOS version it supports.

The script also prints a SHA-256 hash for the file.

**Windows build on GitHub:** you don't need a Windows PC. Create the release (a draft is fine) with its tag, then run the **Release build** workflow from the Actions tab with that tag. It builds `RapydShare.exe` from the commit the release points at, attaches it, and fills in its checksum if the release notes contain `ADD-AFTER-WINDOWS-BUILD`.

**Version number:** update `version_info.txt` (`filevers`, `prodvers`, `FileVersion`, and `ProductVersion`). `build.py` reads `ProductVersion` for the macOS app as well.

**macOS Python:** build with a Python from [python.org](https://www.python.org/downloads/macos/) or `uv python install`, not Homebrew's or pyenv's. Those are built for your exact macOS version, so the app won't open on older Macs. `build.py` warns you if this happens.

**macOS icon:** `assets/RapydShare.icns` is generated from the Windows icon by `python make_mac_icon.py`, which needs macOS. For a sharper icon, pass a larger transparent PNG, for example `python make_mac_icon.py artwork.png`.

## 📄 License

[MIT](LICENSE) © Aayush Jamuar
