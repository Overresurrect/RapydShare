import PyInstaller.__main__
import os
import sys
import re
import shutil
import hashlib
import platform
import plistlib
import subprocess
import sysconfig
from importlib import metadata

IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

# --- HELPER: Find Python's DLLs folder (Windows) ---
# This finds C:\Python310\DLLs or venv\Lib\site-packages\...
def get_python_dlls_path():
    # Attempt to find the standard DLLs folder in the python installation
    base_path = os.path.dirname(sys.executable)
    dll_path = os.path.join(base_path, "DLLs")

    if not os.path.exists(dll_path):
        # Fallback for some venv structures: check one level up
        base_path = os.path.dirname(base_path)
        dll_path = os.path.join(base_path, "DLLs")

    return dll_path

# --- HELPER: Read the app version from version_info.txt ---
def get_app_version():
    with open("version_info.txt", encoding="utf-8") as f:
        match = re.search(r"StringStruct\(u'ProductVersion', u'([\d.]+)'\)", f.read())
    return match.group(1) if match else "0.0.0"

# --- HELPER: Oldest macOS the bundled Python and libraries all support ---
def parse_macos_version(text):
    parts = [int(p) for p in text.split(".")] + [0]
    return tuple(parts[:2])

def get_python_macos_target():
    return parse_macos_version(sysconfig.get_config_var("MACOSX_DEPLOYMENT_TARGET") or "11.0")

def get_min_macos_version():
    # Every installed wheel declares a minimum macOS in its tag; the app needs the highest one
    versions = [get_python_macos_target()]
    for dist in metadata.distributions():
        wheel = dist.read_text("WHEEL") or ""
        for major, minor in re.findall(r"macosx_(\d+)_(\d+)_", wheel):
            versions.append((int(major), int(minor)))
    major, minor = max(versions)
    return f"{major}.{minor}"

# --- PREPARE ARGUMENTS ---
build_args = [
    'main.py',
    '--noconsole',
    '--name=RapydShare',

    # 1. Frontend & Assets
    f'--add-data=frontend/dist{os.pathsep}frontend/dist',
    f'--add-data=assets{os.pathsep}assets',

    # 2. Hidden Imports (The usual suspects)
    '--hidden-import=PyQt6',
    '--hidden-import=qfluentwidgets',
    '--hidden-import=uvicorn',
    '--hidden-import=uvicorn.logging',
    '--hidden-import=uvicorn.loops',
    '--hidden-import=uvicorn.loops.auto',
    '--hidden-import=uvicorn.protocols',
    '--hidden-import=uvicorn.protocols.http',
    '--hidden-import=uvicorn.protocols.http.auto',
    '--hidden-import=uvicorn.lifespan',
    '--hidden-import=uvicorn.lifespan.on',
    '--hidden-import=engineio.async_drivers.aiohttp',

    # 3. Explicitly import XML modules
    '--hidden-import=xml',
    '--hidden-import=xml.parsers.expat',
]

if IS_WINDOWS:
    build_args += [
        '--onefile',
        '--icon=assets/RapydShare.ico',
        '--version-file=version_info.txt',
    ]

    # --- COLLECT BINARIES ---
    # We will manually find all .pyd and .dll files in the Python DLLs folder
    # and tell PyInstaller to include them.
    dll_folder = get_python_dlls_path()

    if os.path.exists(dll_folder):
        print(f"✅ Found Python DLLs at: {dll_folder}")
        # Grab all .pyd and .dll files
        for file in os.listdir(dll_folder):
            if file.endswith(".pyd") or file.endswith(".dll"):
                full_path = os.path.join(dll_folder, file)
                # 4. Inject the brute-forced binaries ('SourcePath;.' puts them in the root of the exe)
                build_args.append(f'--add-binary={full_path};.')
    else:
        print("⚠️  WARNING: Could not auto-detect Python DLLs folder. Build might fail.")

elif IS_MAC:
    # --noconsole produces RapydShare.app; onedir (the default) is the supported layout for an .app
    build_args += [
        '--noconfirm',
        '--icon=assets/RapydShare.icns',
        '--osx-bundle-identifier=com.arthosx.rapydshare',
    ]

    python_target = get_python_macos_target()
    if python_target[0] > 13:
        print(f"⚠️  WARNING: This Python only supports macOS {python_target[0]}.{python_target[1]}+, "
              "so the app won't open on older Macs. Build with a python.org or uv-installed Python instead.")

# --- RUN BUILD ---
print("🚀 Starting Build...")
PyInstaller.__main__.run(build_args)

# --- MAC PACKAGING ---
def finish_mac_app(app_path):
    # PyInstaller has no CLI flags for these Info.plist keys, so patch them in
    plist_path = os.path.join(app_path, "Contents", "Info.plist")
    with open(plist_path, "rb") as f:
        info = plistlib.load(f)

    version = get_app_version()
    info.update({
        "CFBundleShortVersionString": version,
        "CFBundleVersion": version,
        "LSMinimumSystemVersion": get_min_macos_version(),
        "NSLocalNetworkUsageDescription": "RapydShare shares files with devices on your local network.",
        # Files the app writes (uploads) are quarantined, so macOS warns before opening them
        "LSFileQuarantineEnabled": True,
    })

    with open(plist_path, "wb") as f:
        plistlib.dump(info, f)

    # Editing Info.plist invalidates PyInstaller's ad-hoc signature; without re-signing, macOS calls the app "damaged"
    subprocess.run(["codesign", "--force", "--sign", "-", app_path], check=True)

def make_dmg(app_path, dmg_path):
    # Put the app next to an Applications shortcut so users can drag it across to install
    staging = os.path.join("build", "dmg")
    shutil.rmtree(staging, ignore_errors=True)
    os.makedirs(staging)
    subprocess.run(["ditto", app_path, os.path.join(staging, "RapydShare.app")], check=True)
    os.symlink("/Applications", os.path.join(staging, "Applications"))

    subprocess.run(["hdiutil", "create", "-volname", "RapydShare", "-srcfolder", staging,
                    "-format", "UDZO", "-ov", dmg_path], check=True)

if IS_MAC:
    app_path = os.path.join("dist", "RapydShare.app")
    output_path = os.path.join("dist", f"RapydShare-mac-{platform.machine()}.dmg")
    finish_mac_app(app_path)
    make_dmg(app_path, output_path)
else:
    output_path = os.path.join("dist", "RapydShare.exe")

# --- HASH CALCULATION ---
def get_file_hash(filename):
    sha256_hash = hashlib.sha256()
    try:
        with open(filename, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except FileNotFoundError:
        return "File not found"

if os.path.exists(output_path):
    print("\n" + "="*60)
    print(f"BUILD SUCCESSFUL!")
    print(f"File: {output_path}")
    print(f"SHA256: {get_file_hash(output_path)}")
    if IS_MAC:
        print(f"Minimum macOS: {get_min_macos_version()}")
    print("="*60 + "\n")
