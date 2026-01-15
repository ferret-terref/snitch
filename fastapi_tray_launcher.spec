# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:\\Users\\James\\Git\\gallery-arr/fastapi_tray_launcher.py'],
    pathex=[],
    binaries=[],
    datas=[('C:\\Users\\James\\Git\\gallery-arr\\config.yaml', '.'), ('C:\\Users\\James\\Git\\gallery-arr\\static\\index.html', 'static')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='fastapi_tray_launcher',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='fastapi_tray_launcher',
)
