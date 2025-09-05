@echo off
REM =====================================================================
REM GrafTrail Windows Build Script
REM =====================================================================
REM This script builds Windows executables for both GrafTrail versions
REM Requirements: Python 3.9+, pip, virtual environment support

echo =====================================================================
echo Building GrafTrail for Windows
echo =====================================================================

REM Get the script directory
set SCRIPT_DIR=%~dp0
set PROJECT_ROOT=%SCRIPT_DIR%..
set BUILD_DIR=%PROJECT_ROOT%\build_windows
set DIST_DIR=%PROJECT_ROOT%\dist_windows

REM Create and activate virtual environment
echo Creating virtual environment...
python -m venv "%BUILD_DIR%\venv"
call "%BUILD_DIR%\venv\Scripts\activate.bat"

REM Upgrade pip and install dependencies
echo Installing dependencies...
python -m pip install --upgrade pip
pip install -r "%PROJECT_ROOT%\requirements.txt"

REM Clean previous builds
echo Cleaning previous builds...
if exist "%DIST_DIR%" rmdir /s /q "%DIST_DIR%"
if exist "%BUILD_DIR%\build" rmdir /s /q "%BUILD_DIR%\build"
mkdir "%DIST_DIR%"

REM Build main application
echo Building GrafTrail main application...
pyinstaller --clean --noconfirm ^
    --specpath "%BUILD_DIR%" ^
    --workpath "%BUILD_DIR%\build" ^
    --distpath "%DIST_DIR%" ^
    "%PROJECT_ROOT%\build_configs\graftrail_app.spec"

REM Build overlay application
echo Building GrafTrail overlay application...
pyinstaller --clean --noconfirm ^
    --specpath "%BUILD_DIR%" ^
    --workpath "%BUILD_DIR%\build" ^
    --distpath "%DIST_DIR%" ^
    "%PROJECT_ROOT%\build_configs\graftrail_overlay.spec"

REM Create portable package
echo Creating portable package...
set PACKAGE_DIR=%DIST_DIR%\GrafTrail-Windows-Portable
mkdir "%PACKAGE_DIR%"
copy "%DIST_DIR%\GrafTrail.exe" "%PACKAGE_DIR%\"
copy "%DIST_DIR%\GrafTrail-Overlay.exe" "%PACKAGE_DIR%\"
copy "%PROJECT_ROOT%\README.md" "%PACKAGE_DIR%\"

REM Create zip archive
echo Creating zip archive...
powershell "Compress-Archive -Path '%PACKAGE_DIR%' -DestinationPath '%DIST_DIR%\GrafTrail-Windows.zip' -Force"

REM Deactivate virtual environment
deactivate

echo =====================================================================
echo Build completed successfully!
echo =====================================================================
echo Executables location: %DIST_DIR%
echo Portable package: %DIST_DIR%\GrafTrail-Windows.zip
echo =====================================================================

pause
