@echo off
cd /d "%~dp0"

echo =======================================================
echo  Code2Tab Debug Launcher
echo =======================================================
echo.

echo [Step 1] Checking Python...
python --version
if %errorlevel% neq 0 goto ERROR_PYTHON

echo [Step 2] Checking Virtual Environment...
if exist ".venv" goto CHECK_DEPS

echo [Step 3] Creating Virtual Environment (.venv)...
python -m venv .venv
if %errorlevel% neq 0 goto ERROR_VENV

echo [Step 4] Activating and Installing Requirements...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip uv setuptools wheel
uv pip install -r requirements.txt
uv pip install basic-pitch --no-deps
if %errorlevel% neq 0 goto ERROR_INSTALL
goto RUN

:CHECK_DEPS
echo Found existing .venv. Activating...
call .venv\Scripts\activate.bat
echo Checking for missing packages...
python -m pip install uv --quiet
uv pip install -r requirements.txt --quiet
uv pip install basic-pitch --no-deps --quiet

:RUN
echo [Step 5] Running Streamlit App...
echo.
echo Starting server... Please wait...
echo If browser does not open, visit: http://localhost:8501
echo.

python -m streamlit run app.py
if %errorlevel% neq 0 goto ERROR_RUN

echo App process ended.
pause
exit /b

:ERROR_PYTHON
echo.
echo [CRITICAL ERROR] Python command not found!
echo Please install Python from python.org and check "Add Python to environment variables".
pause
exit /b

:ERROR_VENV
echo.
echo [CRITICAL ERROR] Failed to create virtual environment!
pause
exit /b

:ERROR_INSTALL
echo.
echo [CRITICAL ERROR] Failed to install requirements!
pause
exit /b

:ERROR_RUN
echo.
echo [CRITICAL ERROR] The app crashed or failed to start!
pause
exit /b
