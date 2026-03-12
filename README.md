# 🎸 Code2Tab

音声ファイルをアップロードするだけで、AI と音響解析のハイブリッド推定によって **コード進行を自動認識**し、**ギタータブ譜と MIDI** を生成するアプリです。

---

## 機能

- **コード認識** — BTC Transformer (ISMIR19) + Librosa 音響解析 + Basic Pitch MIDI 逆算の 3 エンジンによるハイブリッド推定
- **タブ譜生成** — 認識したコードをギタータブ譜（ASCII）に変換。スタンダード / パワーコードを切り替え可能
- **インタラクティブ再生** — 音声プレイヤーと同期したコードカード表示。再生位置に合わせてハイライト
- **ポジション調整** — 各コードカードのフレットポジションを ▼ / ▲ で手動シフト、↺ でリセット
- **タイミング調整** — グローバルオフセット（±0.1 s / ±0.05 s）と個別コードのタイミングを微調整
- **MIDI 出力** — レベル 3 で Basic Pitch を使用した MIDI ファイルのダウンロード

---

## 技術スタック

| 役割 | ライブラリ / モデル |
|---|---|
| UI フレームワーク | Streamlit |
| AI コード認識 | BTC Transformer (ISMIR19、25 クラス、CQT 特徴量) |
| 音響解析 | Librosa (HPSS、chroma_cqt、chroma_cens、ビート追跡、オンセット検出) |
| ピアノ音域 MIDI 生成 | Basic Pitch (Spotify) |
| MIDI 処理 | pretty_midi、midiutil |
| 深層学習ランタイム | PyTorch |

---

## 精度を上げるコツ

**ギター単体の音源を入力すると精度が大幅に向上します。**

ドラム・ベース・ボーカルが混在した楽曲をそのまま入力するよりも、事前に音源分離ツールでギタートラックだけを抽出してから入力することを推奨します。

| ツール | 説明 |
|---|---|
| [Demucs](https://github.com/facebookresearch/demucs) | Meta 製の高品質音源分離モデル。`other.wav` がギター + シンセを含むトラック |
| [LALAL.AI](https://www.lalal.ai/) | ブラウザで手軽に音源分離できるオンラインサービス |
| [Spleeter](https://github.com/deezer/spleeter) | Deezer 製の高速音源分離ツール |


---

## 解析レベル

サイドバーのスライダーで 1〜3 から選択します。

| レベル | モード | 使用エンジン | 特徴 |
|---|---|---|---|
| 1 | ⚡ 高速 | BTC のみ | 最速。MIDI 生成なし |
| 2 | ⚖️ バランス（推奨） | BTC + Librosa | 速度と精度のバランスが最良。MIDI 生成なし |
| 3 | 🎯 高精度 | BTC + Librosa + Basic Pitch | 最高精度。処理時間が 2〜5 倍増加。MIDI ダウンロード可 |

---

## インストール & 起動（開発環境）

Python 3.12 以上が必要です。

```bash
# 1. 仮想環境を作成して有効化
python -m venv .venv
.venv\Scripts\activate       # Windows
# source .venv/bin/activate  # macOS / Linux

# 2. 依存パッケージをインストール
pip install -r requirements.txt
pip install basic-pitch

# 3. アプリを起動
streamlit run app.py
```

ブラウザで `http://localhost:8501` が開きます。

---

## スタンドアロン配布ビルド（Windows）

Python 不要の `.exe` として配布できます。pywebview + PyInstaller を使用します。

### 必要条件

- Windows 10 / 11
- Python 3.12（`.venv` が作成済みで依存インストール済み）
- `dist_pywebview/` フォルダ内で作業

### ビルド手順

```bat
cd dist_pywebview
build.bat
```

ビルドが完了すると `dist_pywebview\dist\Code2Tab\` に成果物が出力されます。  
`Code2Tab.exe` をダブルクリックするだけで起動します。

### 配布方法

`dist\Code2Tab\` フォルダ全体を zip に固めて配布してください（約 800 MB〜1.2 GB）。

> **補足**: ビルドには PySide6 / Qt バックエンドを使用しています。  
> pywebview 6.x の Windows バックエンドは Qt か WinForms（pythonnet 必須）の 2 択ですが、  
> Python 3.12 では pythonnet のビルドが安定しないため Qt に統一しています。

---

## プロジェクト構成

```
Code2tab/
├── app.py                   # Streamlit メインアプリ
├── requirements.txt         # Python 依存パッケージ
├── run_app.bat              # 開発起動スクリプト
├── src/
│   ├── chord_analyser.py    # コード推定エンジン（BTC / Librosa / Basic Pitch）
│   ├── tab_generator.py     # タブ譜・コードフォーム生成
│   └── BTC/                 # BTC Transformer モデル（ISMIR19）
│       ├── btc_model.py
│       ├── utils/
│       └── test/
│           ├── btc_model.pt          # 標準ボキャブラリモデル
│           └── btc_model_large_voca.pt
└── dist_pywebview/          # スタンドアロンビルド一式
    ├── launcher.py          # pywebview ランチャー
    ├── build.spec           # PyInstaller スペックファイル
    ├── build.bat            # ワンクリックビルドスクリプト
    └── hooks/               # PyInstaller カスタムフック
```

---

## BTC モデルについて

[BTC-ISMIR19](https://github.com/jayg996/BTC-ISMIR19) (Jeong et al., 2019) の事前学習済みモデルを使用しています。  
25 クラス (C, Cm, C#, C#m, ... , B, Bm, N) の双方向 Transformer によるコード認識モデルです。

推論時はモデルの `output_projection` 層から直接ソフトマックス確率を抽出し、Librosa / Basic Pitch の推定スコアと重み付き融合することで精度を向上させています。

---

## ライセンス

© 2026 yuutti

BTC モデル: [MIT License](src/BTC/LICENSE)  
Basic Pitch: [Apache License 2.0](https://github.com/spotify/basic-pitch/blob/main/LICENSE)
