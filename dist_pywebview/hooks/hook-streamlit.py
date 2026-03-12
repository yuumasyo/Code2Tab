# hooks/hook-streamlit.py
# Streamlit の静的アセット・テンプレート・設定ファイルを収集する
from PyInstaller.utils.hooks import collect_all, collect_data_files

datas, binaries, hiddenimports = collect_all('streamlit')
