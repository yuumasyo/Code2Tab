from PyInstaller.utils.hooks import collect_all

# モデルファイル (.onnx, .pb, .bin, .tflite, .mlmodel) を含む全リソースを収集
datas, binaries, hiddenimports = collect_all('basic_pitch')
