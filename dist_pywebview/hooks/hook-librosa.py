# hooks/hook-librosa.py
# librosa が内部で使う全データファイルと依存パッケージを収集する
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = collect_all('librosa')
