# -*- mode: python ; coding: utf-8 -*-
"""
Chord2Tab PyInstaller spec
=========================
ビルドコマンド (dist_pywebview/ ディレクトリで実行):
    pyinstaller build.spec --clean --noconfirm

出力:
    dist_pywebview/dist/Chord2Tab/      ← 配布する一式ディレクトリ
    dist_pywebview/dist/Chord2Tab.exe   ← ランチャー実行ファイル

注意:
  - PyTorch を含むため、ビルド成果物は 800MB〜1.2GB になります。
  - onefile ビルドは起動のたびに展開が走り非常に遅くなるため使用しません。
  - UPX は PyTorch の DLL を破損させる可能性があるため無効にしています。
"""

import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_all, collect_submodules

# ── パス設定 ─────────────────────────────────────────────────────────────────
# spec ファイルは dist_pywebview/ に置かれることを想定
SPEC_DIR  = Path(SPECPATH)                    # dist_pywebview/
ROOT      = SPEC_DIR.parent.resolve()         # プロジェクトルート (app.py がある場所)

# ── データファイル収集 ────────────────────────────────────────────────────────
datas = []

# Streamlit: 静的ファイル・テンプレート等が多数必要
datas += collect_data_files('streamlit', include_py_files=False)

# basic_pitch のモデルファイル
try:
    datas += collect_data_files('basic_pitch')
except Exception:
    pass
datas += collect_data_files('altair')
try:
    datas += collect_data_files('vega_datasets')
except Exception:
    pass

# librosa のデータファイル (音響モデルなど)
datas += collect_data_files('librosa')

# PySide6 / Qt WebEngine (HTML レンダリングエンジン)
datas += collect_data_files('PySide6')
try:
    datas += collect_data_files('qtpy')
except Exception:
    pass

# プロジェクト本体: app.py と src/ ディレクトリ丸ごと
datas += [
    (str(ROOT / 'app.py'),  '.'),           # _MEIPASS/app.py
    (str(ROOT / 'src'),     'src'),          # _MEIPASS/src/
]

# ── 隠れた import の手動補完 ──────────────────────────────────────────────────
hiddenimports = [
    # Streamlit コア
    'streamlit',
    'streamlit.web.cli',
    'streamlit.web.bootstrap',
    'streamlit.runtime',
    'streamlit.runtime.scriptrunner',
    'streamlit.runtime.scriptrunner.magic_funcs',
    'streamlit.runtime.caching',
    'streamlit.runtime.caching.storage',
    'streamlit.components.v1',
    'streamlit.runtime.stats',
    'streamlit.runtime.uploaded_file_manager',
    'streamlit.elements',
    'altair',
    'pyarrow',
    'pydeck',
    # pywebview バックエンド (Qt/PySide6 — Python 3.12 で pythonnet 不要の唯一の安定策)
    'webview',
    'webview.platforms.qt',
    'qtpy',
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    'PySide6.QtNetwork',
    'PySide6.QtWebChannel',
    'PySide6.QtWebEngineCore',
    'PySide6.QtWebEngineWidgets',
    'PySide6.QtWebEngineQuick',
    # 音響解析
    'librosa',
    'librosa.core',
    'librosa.effects',
    'librosa.feature',
    'librosa.onset',
    'librosa.beat',
    'soundfile',
    'resampy',
    'numba',
    'numba.core',
    'numba.typed',
    # 機械学習
    'sklearn',
    'sklearn.utils._cython_blas',
    'sklearn.neighbors._partition_nodes',
    'sklearn.utils._typedefs',
    'sklearn.tree._utils',
    'sklearn.tree._criterion',
    'sklearn.ensemble._forest',
    'cachetools',
    # MIDI / ピアノ音源解析
    'pretty_midi',
    'midiutil',
    'basic_pitch',
    'basic_pitch.inference',
    'basic_pitch.models',
    'basic_pitch.note_creation',
    'basic_pitch.constants',
    # その他
    'yaml',
    'pyyaml',
    'mir_eval',
    'scipy',
    'scipy.signal',
    'sounddevice',
    'demucs',
    'torchaudio',
    'julius',
    'einops',
    'omegaconf',
    'antlr4',
]
# torch サブモジュールの一部は自動検出されないことがある
hiddenimports += collect_submodules('torch')

# basic_pitch の全サブモジュールを収集
try:
    hiddenimports += collect_submodules('basic_pitch')
except Exception:
    pass

# ── 除外するパッケージ (サイズ削減) ──────────────────────────────────────────
excludes = [
    'matplotlib',
    'IPython',
    'jupyter',
    'notebook',
    'nbformat',
    'pytest',
    'sphinx',
    'docutils',
    'pkg_resources._vendor',
    'setuptools',
    'pip',
    'wheel',
    'tkinter',                 # pywebview が使うのは Win32/WinForms
    # 学習用モジュール (推論では不要)
    'tensorboard',
    'tensorflow',
    'tf_logger',
    'torch.utils.tensorboard',
]

# ── バイナリ: PyTorch DLL を明示的に収集 ────────────────────────────────────
binaries = []
try:
    import torch
    torch_lib = Path(torch.__file__).parent / 'lib'
    if torch_lib.exists():
        for dll in torch_lib.glob('*.dll'):
            binaries.append((str(dll), 'torch/lib'))
except ImportError:
    pass

# ── PyInstaller Analysis ──────────────────────────────────────────────────────
a = Analysis(
    [str(SPEC_DIR / 'launcher.py')],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[str(SPEC_DIR / 'hooks')],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,      # one-dir ビルド
    name='Chord2Tab',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                  # PyTorch DLL 破損防止のため UPX 無効
    console=False,              # コンソールウィンドウを非表示
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='../assets/icon.ico',  # アイコンを追加する場合はコメントを外す
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Chord2Tab',
)
