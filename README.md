# RapydShare ⚡

Share files between your computer and any phone, tablet, or laptop on the same Wi-Fi. Pick a folder, click **Start Server**, and open the link (or scan the QR code) in a browser on the other device. There's nothing to install on the other device, and no accounts or cloud services involved.

[![Latest release](https://img.shields.io/github/v/release/Overresurrect/RapydShare)](https://github.com/Overresurrect/RapydShare/releases/latest)
[![License: MIT](https://img.shields.io/github/license/Overresurrect/RapydShare)](LICENSE)
![Platforms](https://img.shields.io/badge/platform-Windows%20%7C%20macOS-blue)

![RapydShare Screenshot](assets/Screenshot.jpg)\
*RapydShare desktop app*

![RapydShare Browser Screenshot](assets/Screenshot-Web.jpg)\
*RapydShare web client*

## 🚀 Features

**Desktop app (the computer sharing files)**

- Share any folder on a port you choose (8000 by default).
- Shows a QR code and copies the link to your clipboard as soon as the server starts.
- Optional username and password so only people you tell can get in.
- Optional uploads: pick a folder where files sent from other devices are saved.
- Dark, Fluent-style interface built with PyQt6 and QFluentWidgets.

**Web client (the other devices)**

- Works in any modern browser, on mobile or desktop.
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

1. **Choose a shared folder.** It starts as your home folder on macOS, or the folder the app was started from on Windows.
2. **(Optional) Change the port** if 8000 is already in use.
3. **(Optional) Turn on Authentication** and set a username and password. The defaults are `admin` / `1234`, so change the password.
4. **(Optional) Turn on Allow Uploads** and choose a folder to receive files. Uploads always go into this folder, whatever folder the sender is browsing. They only show up in the web client if this folder is inside the shared folder, and the app warns you if it isn't.
5. Click **Start Server**.
6. On the other device, scan the QR code or open the link the app shows, for example `http://192.168.1.20:8000`. Include the port number.

Click **Stop Server** when you're done. The settings are locked while the server is running.

Some things to know:

- Uploaded files never overwrite each other. If a file with the same name already exists, the new one is saved as `name (1).ext`, `name (2).ext`, and so on.
- When you download a folder, RapydShare builds the whole ZIP before the download starts, so big folders can take a moment.

## 🔒 Security

RapydShare is meant for networks you trust, like your home Wi-Fi.

- Connections use plain HTTP, not HTTPS, so RapydShare doesn't encrypt what's being transferred.
- Without Authentication, anyone who can reach your computer on that port can browse and download from the shared folder. If you're on a shared network, turn Authentication on.
- Authentication uses HTTP Basic auth, and the browser asks for the username and password. Because the connection is plain HTTP, the password isn't encrypted either, so don't reuse an important one.
- Uploads are off by default. Turn them on only while you need them.
- Stop the server when you're finished sharing.

## 🩺 Troubleshooting

**The link doesn't load on my phone.**

- Make sure both devices are on the same network. Guest Wi-Fi networks often block devices from reaching each other.
- Check that you allowed RapydShare through the firewall (Windows) or allowed local network access (macOS).
- If you're on a VPN, the link may show the VPN's address instead of your Wi-Fi address. Turn the VPN off, or use your computer's Wi-Fi IP address with the same port.
- Another app may already be using the port. Stop the server, change the port, and start it again.

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

- Python 3.10 or newer
- Node.js 20.19+ or 22.12+ (required by Vite 7), with npm

### Setup

```bash
git clone https://github.com/Overresurrect/RapydShare.git
cd RapydShare

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

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

### Work on the web client

For live reloading, start the server from the desktop app on port **8000**, then run the Vite dev server in a second terminal:

```bash
cd frontend
npm run dev
```

Open `http://localhost:5173`. Vite forwards `/api` requests to `http://127.0.0.1:8000`. Use `npm run lint` to lint the frontend.

### Project structure

```text
main.py              Entry point: starts the Qt app
src/gui.py           Desktop window: settings, QR code, start/stop
src/server.py        FastAPI server: file API and web client hosting
src/config.py        Settings shared by the GUI and server
src/utils.py         Local IP lookup, QR codes, thumbnails
frontend/            React web client
build.py             PyInstaller build for Windows and macOS
make_mac_icon.py     Generates the macOS icon
version_info.txt     App version and Windows file metadata
```

<details>
<summary>API endpoints</summary>

All endpoints take a `path` relative to the shared folder, and require Basic auth when Authentication is on.

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/api/files?path=` | Lists a folder |
| `GET` | `/api/thumb?path=` | JPEG thumbnail of an image or video |
| `GET` | `/api/view?path=` | Serves a file inline, for previews |
| `GET` | `/api/download?path=` | Downloads a file |
| `GET` | `/api/download_folder?path=` | Downloads a folder as a ZIP |
| `GET` | `/api/server_info` | Returns `{ "allow_upload": bool }` |
| `POST` | `/api/upload` | Uploads one file (multipart field `file`) |

</details>

### Build a release

Build on the platform you're targeting. PyInstaller can't cross-compile.

```bash
cd frontend
npm run build
cd ..
python build.py
```

The output lands in `dist/`:

- **Windows:** `RapydShare.exe`, a single-file app.
- **macOS:** `RapydShare.app` and `RapydShare-mac-arm64.dmg`, ready to upload to a release. The script ad-hoc signs the app and prints the minimum macOS version it supports.

The script also prints a SHA-256 hash for the file.

**Version number:** update `version_info.txt` (`filevers`, `prodvers`, `FileVersion`, and `ProductVersion`). `build.py` reads `ProductVersion` for the macOS app as well.

**macOS Python:** build with a Python from [python.org](https://www.python.org/downloads/macos/) or `uv python install`, not Homebrew's or pyenv's. Those are built for your exact macOS version, so the app won't open on older Macs. `build.py` warns you if this happens.

**macOS icon:** `assets/RapydShare.icns` is generated from the Windows icon by `python make_mac_icon.py`, which needs macOS. For a sharper icon, pass a larger transparent PNG, for example `python make_mac_icon.py artwork.png`.

## 📄 License

[MIT](LICENSE) © Aayush Jamuar
