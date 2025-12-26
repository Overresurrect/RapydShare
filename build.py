import PyInstaller.__main__
import os
import sys
import hashlib
import glob

# --- HELPER: Find Python's DLLs folder ---
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

# --- COLLECT BINARIES ---
# We will manually find all .pyd and .dll files in the Python DLLs folder
# and tell PyInstaller to include them.
dll_folder = get_python_dlls_path()
extra_binaries = []

if os.path.exists(dll_folder):
    print(f"✅ Found Python DLLs at: {dll_folder}")
    # Grab all .pyd and .dll files
    for file in os.listdir(dll_folder):
        if file.endswith(".pyd") or file.endswith(".dll"):
            full_path = os.path.join(dll_folder, file)
            # Format: 'SourcePath;.' (dot means put in root of exe)
            extra_binaries.append(f'{full_path};.')
else:
    print("⚠️  WARNING: Could not auto-detect Python DLLs folder. Build might fail.")

# --- PREPARE ARGUMENTS ---
build_args = [
    'main.py',
    '--noconsole',
    '--onefile',
    '--name=RapydShare',
    '--icon=assets/RapydShare.ico',
    '--version-file=version_info.txt',
    
    # 1. Frontend & Assets
    '--add-data=frontend/dist;frontend/dist', 
    '--add-data=assets;assets',

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

# 4. Inject the brute-forced binaries
for binary in extra_binaries:
    build_args.append(f'--add-binary={binary}')

# --- RUN BUILD ---
print("🚀 Starting Build with Brute Force DLL Inclusion...")
PyInstaller.__main__.run(build_args)

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

exe_path = os.path.join("dist", "RapydShare.exe")

if os.path.exists(exe_path):
    print("\n" + "="*60)
    print(f"BUILD SUCCESSFUL!")
    print(f"File: {exe_path}")
    print(f"SHA256: {get_file_hash(exe_path)}")
    print("="*60 + "\n")