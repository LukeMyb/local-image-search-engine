@echo off
title Image Update Pipeline (GPU Worker)

REM Move to the project root directory (one level up from tasks/)
cd /d "%~dp0.."

REM Activate the Python virtual environment
if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
) else (
    echo [ERROR] Virtual environment not found at .venv\Scripts\activate.bat
    pause
    exit /b 1
)

echo ============================================================
echo [Phase 1] Scanning image folder and registering to database
echo ============================================================
python -m tasks.index --scan-only
if errorlevel 1 (
    echo [ERROR] Image scan failed. Aborting pipeline.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo [Phase 2] Starting CPU and GPU tasks in parallel
echo   - New Window (CPU) : tasks.index --thumb-only
echo   - This Window (GPU): tasks.tagger -^> tasks.vectorize_images
echo ============================================================
echo.

REM Launch CPU-bound thumbnail generation in a separate window
start "Thumbnail Generator (CPU)" cmd /c "call .venv\Scripts\activate.bat && python -m tasks.index --thumb-only && echo. && echo [CPU Task] Thumbnail generation finished. && pause"

REM Run GPU-bound tasks sequentially in the current window
echo [GPU Task 1/2] Running AI Tagger (tasks.tagger)...
python -m tasks.tagger
if errorlevel 1 (
    echo [ERROR] AI Tagger encountered an error.
    pause
    exit /b 1
)

echo.
echo [GPU Task 2/2] Running Style Vectorizer (tasks.vectorize_images)...
python -m tasks.vectorize_images
if errorlevel 1 (
    echo [ERROR] Style Vectorizer encountered an error.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo [GPU Tasks Completed] Tagger and Style Vectorizer finished!
echo ============================================================
pause
