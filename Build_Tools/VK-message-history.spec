# -*- coding: utf-8 -*-
import os
import sys
from pathlib import Path

block_cipher = None

# ========================================================
# 🔧 CONFIGURATION SECTION
# ========================================================
SMOKE_BUILD = os.environ.get('VK_FROZEN_SMOKE_BUILD') == '1'
DIAGNOSTIC_BUILD = os.environ.get('VK_FROZEN_DIAGNOSTIC_BUILD') == '1'
APP_NAME = ('VK-message-history-smoke' if SMOKE_BUILD else
            'VK-message-history-diagnostic' if DIAGNOSTIC_BUILD else 'VK-message-history')
MAIN_SCRIPT = 'Build_Tools/frozen_smoke.py' if SMOKE_BUILD else 'process_all_vk.pyw'
ICON_FILE = 'logo.ico'      # e.g., 'logo.ico' or None

# List of hidden imports (modules that PyInstaller cannot detect)
HIDDEN_IMPORTS = [
    # 'uvicorn',
    # 'pydantic',
]

# List of extra data files to include INSIDE the exe (src, dst)
# Note: For external config files, use post_build.py instead.
ADDED_FILES = [
    ('logo.ico', '.'),
]
# ========================================================

spec_path = os.path.abspath(sys.argv[0])
spec_dir = os.path.dirname(spec_path)
project_root = os.path.abspath(os.path.join(spec_dir, '..'))

# Resolve paths
script_path = os.path.join(project_root, MAIN_SCRIPT)
icon_path = os.path.join(project_root, ICON_FILE) if ICON_FILE else None

# Collect resources for specific libraries if needed
# Example: tmp_ret = collect_all('some_lib')
# datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

a = Analysis(
    [script_path],
    pathex=[project_root],
    binaries=[],
    datas=ADDED_FILES,
    hiddenimports=HIDDEN_IMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# PyInstaller ищет DLL через PATH. Сборка прерывается, если она нашла бинарник
# вне проекта, выбранного Python/venv или системного каталога Windows.
trusted_roots = [
    Path(project_root), Path(sys.prefix), Path(sys.base_prefix),
    Path(os.environ['SystemRoot']),
]
trusted_roots = [os.path.normcase(str(path.resolve())) for path in trusted_roots]

def is_trusted(source):
    resolved = os.path.normcase(str(Path(source).resolve()))
    for root in trusted_roots:
        try:
            if os.path.commonpath([resolved, root]) == root:
                return True
        except ValueError:  # источник и разрешённый каталог на разных дисках
            continue
    return False

# Qt поставляет согласованный комплект MSVC runtime. Не смешиваем его с более
# старым комплектом из базовой установки Python.
qt_runtime = Path(sys.prefix) / 'Lib' / 'site-packages' / 'PySide6'
runtime_names = [
    'concrt140.dll', 'msvcp140.dll', 'msvcp140_1.dll',
    'msvcp140_2.dll', 'msvcp140_codecvt_ids.dll', 'vcamp140.dll',
    'vccorlib140.dll', 'vcomp140.dll', 'vcruntime140.dll',
    'vcruntime140_1.dll',
]
for name in runtime_names:
    if not (qt_runtime / name).is_file():
        raise RuntimeError(f'Отсутствует Qt MSVC runtime: {qt_runtime / name}')

root_runtime = set()
for index, (destination, source, kind) in enumerate(a.binaries):
    name = Path(destination).name.lower()
    if name in runtime_names and str(Path(destination).parent) in ('.', ''):
        a.binaries[index] = (destination, str(qt_runtime / name), kind)
        root_runtime.add(name)
for name in runtime_names:
    if name not in root_runtime:
        a.binaries.append((name, str(qt_runtime / name), 'BINARY'))

for destination, source, kind in a.binaries:
    if not is_trusted(source):
        raise RuntimeError(f'Недоверенный бинарник {destination}: {source}')

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=SMOKE_BUILD or DIAGNOSTIC_BUILD,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME,
)
