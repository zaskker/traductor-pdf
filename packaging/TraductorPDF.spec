# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

import os
PROJECT_ROOT = os.path.abspath(os.path.join(SPECPATH, '..'))

a = Analysis(
    [os.path.join(PROJECT_ROOT, 'launcher.py')],
    pathex=[PROJECT_ROOT],
    binaries=[],
    datas=[],
    hiddenimports=[
        'pymupdf',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pytest', 'pytestqt', 'matplotlib', 'numpy', 'scipy', 'IPython'], # Excluir librerias cientificas y dev para ahorrar tamano
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='TraductorPDF',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False, # Windowed app, oculta consola en UI, pero si usas cli muestra exit code/errores
    disable_windowed_traceback=False,
    argv_emulation=True, # Importante para MacOS y util
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='TraductorPDF',
)
