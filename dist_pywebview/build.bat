@echo off
setlocal enabledelayedexpansion
chcp 65001 > nul
cd /d "%~dp0"

echo ============================================================
echo  Chord2Tab ビルドスクリプト (pywebview + PyInstaller)
echo ============================================================
echo.

:: ─── 仮想環境の有効化 ───────────────────────────────────────────────────────
set VENV=%~dp0..\.venv
if not exist "%VENV%\Scripts\activate.bat" (
    echo [ERROR] .venv が見つかりません: %VENV%
    echo         プロジェクトルートで 'python -m venv .venv' を実行してください。
    pause & exit /b 1
)
call "%VENV%\Scripts\activate.bat"
echo [OK] 仮想環境を有効化しました

:: ─── 必須ツールのインストール ────────────────────────────────────────────────
echo.
echo [1/4] pyinstaller と pywebview をインストール中...

rem pywebview 6.x の Windows バックエンドは Qt か WinForms のみ。
rem Python 3.12 では pythonnet ビルドが失敗するため Qt (PySide6) バックエンドを使用。
pip install pyinstaller --quiet
if errorlevel 1 ( echo [ERROR] pyinstaller のインストールに失敗しました & pause & exit /b 1 )

rem pywebview を --no-deps で入れて pythonnet ソースビルドを回避
pip install "pywebview>=4.0" --no-deps --quiet
if errorlevel 1 ( echo [ERROR] pywebview のインストールに失敗しました & pause & exit /b 1 )

rem pywebview 実依存 (pythonnet 除く) + Qt バックエンド
pip install proxy_tools bottle qtpy PySide6 --quiet
if errorlevel 1 ( echo [WARN] PySide6/qtpy のインストールに失敗しました。続行します。)

echo [OK] インストール完了

:: ─── 開発用依存関係の確認 ────────────────────────────────────────────────────
echo.
echo [2/4] プロジェクト依存関係の確認...
pip install -r ..\requirements.txt --quiet
if errorlevel 1 ( echo [WARN] 一部の依存関係のインストールに失敗しました。続行します。)
echo [OK] 依存関係の確認完了

:: ─── 前回のビルドをクリーン ──────────────────────────────────────────────────
echo.
echo [3/4] 前回のビルドをクリーン中...
if exist "dist" (
    powershell -NoProfile -Command "Remove-Item -Path 'dist' -Recurse -Force -ErrorAction SilentlyContinue"
    if exist "dist" rmdir /s /q "dist" 2>nul
)
if exist "build" (
    powershell -NoProfile -Command "Remove-Item -Path 'build' -Recurse -Force -ErrorAction SilentlyContinue"
    if exist "build" rmdir /s /q "build" 2>nul
)
echo [OK] クリーン完了

:: ─── PyInstaller ビルド ──────────────────────────────────────────────────────
echo.
echo [4/4] PyInstaller でビルド中 (数分かかります)...
echo       PyTorch を含むため、成果物は 800MB〜1.2GB になります。
echo.
pyinstaller build.spec --clean --noconfirm
if errorlevel 1 (
    echo.
    echo [ERROR] ビルドに失敗しました。上記のエラー内容を確認してください。
    pause & exit /b 1
)

echo.
echo ============================================================
echo  ビルド完了!
echo  出力先: %~dp0dist\Chord2Tab\
echo.
echo  動作確認:
echo    dist\Chord2Tab\Chord2Tab.exe を実行してください
echo.
echo  配布方法:
echo    dist\Chord2Tab\ ディレクトリ全体を zip に固めて配布
echo    または Inno Setup で .exe インストーラーを作成 (README 参照)
echo ============================================================
pause
