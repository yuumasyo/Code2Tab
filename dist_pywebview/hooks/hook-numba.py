# hooks/hook-numba.py
# numba (librosa の JIT コンパイラ依存) の DLL・データを収集する
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = collect_all('numba')
