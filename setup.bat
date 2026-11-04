@echo off
title Initial Setup Pipeline (GPU Worker)

REM Move to the project root directory
cd /d "%~dp0"

REM Activate the Python virtual environment
if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
) else (
    echo [ERROR] Virtual environment not found at .venv\Scripts\activate.bat
    echo Please create the virtual environment and install dependencies first.
    pause
    exit /b 1
)

echo ============================================================
echo [Phase 1] Scanning image folder and initializing database
echo ============================================================
python -m tasks.index --scan-only
if errorlevel 1 (
    echo [ERROR] Initial image scan failed. Aborting setup.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo [Phase 2] Starting CPU and GPU setup tasks in parallel
echo   - New Window (CPU) : scripts.download_assets -^> tasks.index --thumb-only
echo   - This Window (GPU): scripts.vectorize_tags -^> tasks.tagger -^> tasks.vectorize_images
echo ============================================================
echo.

REM Launch CPU and network-bound tasks in a separate window
start "Initial Setup (CPU Worker)" cmd /c "call .venv\Scripts\activate.bat && echo [CPU Task 1/2] Downloading translation dictionary (scripts.download_assets)... && python -m scripts.download_assets && echo. && echo [CPU Task 2/2] Generating image thumbnails (tasks.index --thumb-only)... && python -m tasks.index --thumb-only && echo. && echo ============================================================ && echo [CPU Setup Tasks Completed] Dictionary and Thumbnails ready! && echo ============================================================ && pause"

REM Run GPU-bound tasks sequentially in the current window
echo [GPU Task 1/3] Vectorizing tag list with CLIP (scripts.vectorize_tags)...
python -m scripts.vectorize_tags
if errorlevel 1 (
    echo [ERROR] Tag vectorization encountered an error.
    pause
    exit /b 1
)

echo.
echo [GPU Task 2/3] Running AI Tagger (tasks.tagger)...
python -m tasks.tagger
if errorlevel 1 (
    echo [ERROR] AI Tagger encountered an error.
    pause
    exit /b 1
)

echo.
echo [GPU Task 3/3] Running Style Vectorizer (tasks.vectorize_images)...
python -m tasks.vectorize_images
if errorlevel 1 (
    echo [ERROR] Style Vectorizer encountered an error.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo [GPU Setup Tasks Completed] All GPU setup steps finished!
echo ============================================================
pause
