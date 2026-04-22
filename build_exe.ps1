# Build script for Migration Analysis Tool executable
# LIGHTWEIGHT VERSION: SCM tools NOT bundled (target: <24MB)
# Users must have RTC SCM CLI (lscm/scm.exe) installed separately

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Migration Analysis Tool - EXE Builder" -ForegroundColor Cyan
Write-Host "LIGHTWEIGHT VERSION (Target: <24MB)" -ForegroundColor Green
Write-Host "SCM tools NOT bundled" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if PyInstaller is installed
Write-Host "Checking PyInstaller installation..." -ForegroundColor Yellow
$pyinstallerCheck = py -m pip show pyinstaller 2>$null

if (-not $pyinstallerCheck) {
    Write-Host "PyInstaller not found. Installing..." -ForegroundColor Yellow
    py -m pip install pyinstaller
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Failed to install PyInstaller!" -ForegroundColor Red
        exit 1
    }
}

Write-Host "PyInstaller is ready!" -ForegroundColor Green
Write-Host ""

# Clean previous builds
Write-Host "Cleaning previous builds..." -ForegroundColor Yellow
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
Write-Host "Clean complete!" -ForegroundColor Green
Write-Host ""

# Build the executable
Write-Host "Building executable with optimizations..." -ForegroundColor Yellow
Write-Host "This may take a few minutes..." -ForegroundColor Gray
Write-Host ""

py -m PyInstaller --clean build_exe.spec

if ($LASTEXITCODE -ne 0) {
    Write-Host "Build failed!" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "Build Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "NOTE: SCM tools NOT bundled for 24MB target" -ForegroundColor Yellow
Write-Host "Users must install RTC SCM CLI separately" -ForegroundColor Yellow
Write-Host ""

# Show final executable size
if (Test-Path "dist\MigrationAnalysisTool.exe") {
    $exeSize = (Get-Item "dist\MigrationAnalysisTool.exe").Length / 1MB
    Write-Host "Final executable size: $([math]::Round($exeSize, 2)) MB" -ForegroundColor Cyan
    Write-Host "Location: dist\MigrationAnalysisTool.exe" -ForegroundColor Cyan
    Write-Host ""
}

# Check the file size
$exePath = "dist\MigrationAnalysisTool.exe"
if (Test-Path $exePath) {
    $fileSize = (Get-Item $exePath).Length
    $fileSizeMB = [math]::Round($fileSize / 1MB, 2)
    
    Write-Host "Executable location: $exePath" -ForegroundColor Cyan
    Write-Host "File size: $fileSizeMB MB" -ForegroundColor Cyan
    Write-Host ""
    
    if ($fileSizeMB -le 24) {
        Write-Host "SUCCESS: File size is within the 24MB limit!" -ForegroundColor Green
    } else {
        Write-Host "WARNING: File size exceeds 24MB limit!" -ForegroundColor Yellow
        Write-Host "Current size: $fileSizeMB MB" -ForegroundColor Yellow
        Write-Host "Consider further optimizations:" -ForegroundColor Yellow
        Write-Host "  - Remove unused dependencies" -ForegroundColor Gray
        Write-Host "  - Exclude more modules in the spec file" -ForegroundColor Gray
        Write-Host "  - Use external dependencies (not bundled)" -ForegroundColor Gray
    }
} else {
    Write-Host "ERROR: Executable not found at expected location!" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Build process completed!" -ForegroundColor Cyan
