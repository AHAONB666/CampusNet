# -*- mode: python ; coding: utf-8 -*-
"""CampusNet PyInstaller spec（跨机器可用版）

路径全部由 SPECPATH 推导，不含任何盘符或绝对路径。
推荐用 build.py 构建（命令行参数驱动，无需本文件）；
本 spec 用于需要 spec 模式的场合：

    python -m PyInstaller CampusNet.spec --noconfirm

产出于 dist/。
"""
import os

ROOT = SPECPATH                            # spec 位于项目根目录
SRC = os.path.join(ROOT, 'src')
ICON = os.path.join(ROOT, 'assets', 'icon.ico')
ENTRY = os.path.join(SRC, 'ui_scifi.py')
DIST = os.path.join(ROOT, 'dist')
WORK = os.path.join(ROOT, '_build', 'work-spec')

a = Analysis(
    [ENTRY],
    pathex=[SRC],
    binaries=[],
    datas=[(ICON, 'assets')],
    hiddenimports=['ui_quiet', 'ui_theme', 'psutil', 'tray'],
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
    name='CampusNet',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON,
)
