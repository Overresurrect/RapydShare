import PyInstaller.__main__
import os

PyInstaller.__main__.run([
    'main.py',
    '--noconsole',
    '--onefile',
    '--name=RapydShare',
    '--icon=assets/RapydShare.ico',
    '--version-file=version_info.txt',
    
    # 1. Include the React Build folder (Must exist now!)
    '--add-data=frontend/dist;frontend/dist', 
    
    # 2. Include Assets
    '--add-data=assets;assets',

    # 3. Hidden Imports for Server & GUI
    '--hidden-import=PyQt6',
    '--hidden-import=qfluentwidgets',
    '--hidden-import=uvicorn.logging',
    '--hidden-import=uvicorn.loops',
    '--hidden-import=uvicorn.loops.auto',
    '--hidden-import=uvicorn.protocols',
    '--hidden-import=uvicorn.protocols.http',
    '--hidden-import=uvicorn.protocols.http.auto',
    '--hidden-import=uvicorn.lifespan',
    '--hidden-import=uvicorn.lifespan.on',
])