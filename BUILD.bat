@echo off
REM Quick Build Script for Windows
REM Builds standalone executable with bundled SCM tools

echo ========================================
echo Migration Analysis Tool - Quick Build
echo ========================================
echo.

cd /d "%~dp0"

echo Checking Python installation...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python not found! Please install Python 3.8+ first.
    pause
    exit /b 1
)

echo.
echo Installing PyInstaller...
python -m pip install pyinstaller

echo.
echo Building executable (this may take 5-10 minutes)...
echo.

pyinstaller --clean build_exe.spec

if %errorlevel% neq 0 (
    echo.
    echo BUILD FAILED!
    pause
    exit /b 1
)

echo.
echo ========================================
echo BUILD SUCCESSFUL!
echo ========================================
echo.

if exist "dist\MigrationAnalysisTool.exe" (
    for %%I in ("dist\MigrationAnalysisTool.exe") do set SIZE=%%~zI
    set /a SIZE_MB=%SIZE%/1048576
    echo Executable created: dist\MigrationAnalysisTool.exe
    echo Size: approximately %SIZE_MB% MB
    echo.
    echo This executable includes:
    echo   - All application code
    echo   - RTC SCM CLI ^(scm.exe^)
    echo   - All dependencies
    echo.
    echo Users can run this .exe without installing LSCM!
    echo.
)

echo Press any key to exit...
pause >nul
