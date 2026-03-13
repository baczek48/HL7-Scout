# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas_oracle,    bins_oracle,    hi_oracle    = collect_all('oracledb')
datas_crypto,    bins_crypto,    hi_crypto    = collect_all('cryptography')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=bins_oracle + bins_crypto,
    datas=[('ui', 'ui')] + datas_oracle + datas_crypto,
    hiddenimports=hi_oracle + hi_crypto,
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
    a.binaries,
    a.datas,
    [],
    name='HL7Scout',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['icon.ico'],
)
