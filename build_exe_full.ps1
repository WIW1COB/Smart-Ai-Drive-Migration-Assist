# Build script for Migration Analysis Tool executable - FULL VERSION
# INCLUDES SCM TOOLS BUNDLED (target: ~150-180 MB)
# Users won't need RTC SCM CLI installed separately

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Migration Analysis Tool - EXE Builder" -ForegroundColor Cyan
Write-Host "FULL VERSION (Target: ~150-180 MB)" -ForegroundColor Green
Write-Host "SCM tools BUNDLED" -ForegroundColor Green
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

# Check for SCM tools
Write-Host "Checking for SCM tools..." -ForegroundColor Yellow
$scmPaths = @(
    "C:\Users\yyy1cob\Desktop\598_Kit_Download_Fail\Migration_Assist\EWM-scmTools-Win64-7.0.3\jazz\scmtools\eclipse",
    "C:\Program Files\IBM\RTC-SCM-CLI\scmtools\eclipse",
    "C:\toolbase\lscm\scmtools\eclipse"
)

$scmFound = $false
foreach ($path in $scmPaths) {
    if (Test-Path $path) {
        Write-Host "✓ SCM tools found at: $path" -ForegroundColor Green
        $scmFound = $true
        break
    }
}

if (-not $scmFound) {
    Write-Host "⚠ WARNING: SCM tools not found at expected locations!" -ForegroundColor Yellow
    Write-Host "  The executable will be built WITHOUT bundled SCM tools." -ForegroundColor Yellow
    Write-Host "  Users will need to install RTC SCM CLI separately." -ForegroundColor Yellow
    Write-Host ""
    $continue = Read-Host "Continue anyway? (y/n)"
    if ($continue -ne "y") {
        Write-Host "Build cancelled." -ForegroundColor Red
        exit 1
    }
}
Write-Host ""

# Clean previous builds
Write-Host "Cleaning previous builds..." -ForegroundColor Yellow
if (Test-Path "dist\MigrationAnalysisTool_Full.exe") { 
    Remove-Item -Force "dist\MigrationAnalysisTool_Full.exe" 
}
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
Write-Host "Clean complete!" -ForegroundColor Green
Write-Host ""

# Build the executable
Write-Host "Building FULL VERSION executable..." -ForegroundColor Yellow
Write-Host "This will take several minutes (bundling SCM tools ~133 MB)..." -ForegroundColor Gray
Write-Host ""

$startTime = Get-Date
py -m PyInstaller --clean build_exe_full.spec

if ($LASTEXITCODE -ne 0) {
    Write-Host "Build failed!" -ForegroundColor Red
    exit 1
}

$endTime = Get-Date
$duration = $endTime - $startTime

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "Build Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

# Show file info
if (Test-Path "dist\MigrationAnalysisTool_Full.exe") {
    $exeInfo = Get-Item "dist\MigrationAnalysisTool_Full.exe"
    $sizeInMB = [math]::Round($exeInfo.Length / 1MB, 2)
    
    Write-Host "Executable Details:" -ForegroundColor Cyan
    Write-Host "  Location: dist\MigrationAnalysisTool_Full.exe" -ForegroundColor White
    Write-Host "  Size: $sizeInMB MB" -ForegroundColor White
    Write-Host "  Build Time: $($duration.Minutes)m $($duration.Seconds)s" -ForegroundColor White
    Write-Host ""
    
    if ($scmFound) {
        Write-Host "✓ SCM tools bundled - users don't need LSCM installed!" -ForegroundColor Green
    } else {
        Write-Host "⚠ SCM tools NOT bundled - users need LSCM installed!" -ForegroundColor Yellow
    }
    
    Write-Host ""
    Write-Host "The executable is ready for distribution!" -ForegroundColor Green
    Write-Host "Just copy 'dist\MigrationAnalysisTool_Full.exe' to target location." -ForegroundColor White
} else {
    Write-Host "ERROR: Executable not found!" -ForegroundColor Red
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
