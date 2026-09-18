# PowerShell script for building and running the Flask Chat Server Docker container
# (aws/Dockerfile.production)
# docker-build.ps1

param(
    [Parameter(Mandatory=$false)]
    [switch]$BuildOnly,

    [Parameter(Mandatory=$false)]
    [switch]$NoCache,

    [Parameter(Mandatory=$false)]
    [switch]$Help
)

# Function to display usage
function Show-Usage {
    Write-Host "Usage: .\docker-build.ps1 [OPTIONS]" -ForegroundColor Blue
    Write-Host "Options:" -ForegroundColor Blue
    Write-Host "  -BuildOnly                  Build only, don't run containers" -ForegroundColor White
    Write-Host "  -NoCache                    Build without using cache" -ForegroundColor White
    Write-Host "  -Help                       Show this help message" -ForegroundColor White
    Write-Host ""
    Write-Host "Examples:" -ForegroundColor Yellow
    Write-Host "  .\docker-build.ps1                                    # Build and run" -ForegroundColor Gray
    Write-Host "  .\docker-build.ps1 -BuildOnly -NoCache               # Build only with no cache" -ForegroundColor Gray
}

# Show help if requested
if ($Help) {
    Show-Usage
    exit 0
}

# This script lives in aws/, but the Dockerfile, docker-compose.chat.yml,
# .env and the build context (".") are all at the repo root - move there
# regardless of the caller's current directory.
Set-Location (Join-Path $PSScriptRoot "..")

Write-Host "🐳 Flask Chat Server Docker Build Script" -ForegroundColor Blue
Write-Host "=========================================" -ForegroundColor Blue
Write-Host "Build only: $BuildOnly" -ForegroundColor Yellow
Write-Host "No cache: $NoCache" -ForegroundColor Yellow
Write-Host ""

# Check if .env file exists
if (-not (Test-Path ".env")) {
    Write-Host "⚠️  Warning: .env file not found. Make sure to create one with your configuration." -ForegroundColor Yellow
    Write-Host ""
}

# Set Docker build args
$BuildArgs = @()
if ($NoCache) {
    $BuildArgs += "--no-cache"
}

try {
    Write-Host "🚀 Building image (aws/Dockerfile.production)..." -ForegroundColor Green
    $dockerCmd = "docker build " + ($BuildArgs -join " ") + " -f aws/Dockerfile.production -t transcribe-chat:prod ."
    Invoke-Expression $dockerCmd

    if (-not $BuildOnly) {
        Write-Host "Starting environment..." -ForegroundColor Blue
        docker-compose -f docker-compose.chat.yml up -d chat-server-prod

        Write-Host "✅ Environment started!" -ForegroundColor Green
        Write-Host "📊 Chat Server: http://localhost:5001" -ForegroundColor Yellow
        Write-Host "🏥 Health Check: http://localhost:5001/health" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "To view logs: docker-compose -f docker-compose.chat.yml logs -f chat-server-prod" -ForegroundColor Blue
        Write-Host "To stop: docker-compose -f docker-compose.chat.yml down" -ForegroundColor Blue
    }

    if ($BuildOnly) {
        Write-Host "✅ Build completed successfully!" -ForegroundColor Green
    }

    Write-Host ""
    Write-Host "🎉 Done!" -ForegroundColor Green

} catch {
    Write-Host "❌ Error occurred: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
