# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

# NOTE:
# - Browser drivers must stay external to the EXE
# - page_address.txt / page_cookie.txt / api.txt must stay external to the EXE
# - The desktop release folder is prepared by package_exe.py after build

datas = []
binaries = []
hiddenimports = ['selenium', 'selenium.webdriver', 'selenium.webdriver.edge', 'selenium.webdriver.chrome', 'selenium.webdriver.firefox', 'requests', 'bs4', 'openai']
tmp_ret = collect_all('selenium')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('bs4')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('openai')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['mooc_robot.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
    name='mooc_robot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
