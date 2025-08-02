# PowerShell script for building and running Flask Chat Server Docker containers
# docker-build.ps1

param(
    [Parameter(Mandatory=$false)]
    [ValidateSet("development", "production")]
    [string]$Environment = "development",
    
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
    Write-Host "  -Environment ENVIRONMENT    Set environment (development|production) [default: development]" -ForegroundColor White
    Write-Host "  -BuildOnly                  Build only, don't run containers" -ForegroundColor White
    Write-Host "  -NoCache                    Build without using cache" -ForegroundColor White
    Write-Host "  -Help                       Show this help message" -ForegroundColor White
    Write-Host ""
    Write-Host "Examples:" -ForegroundColor Yellow
    Write-Host "  .\docker-build.ps1                                    # Build and run development environment" -ForegroundColor Gray
    Write-Host "  .\docker-build.ps1 -Environment production           # Build and run production environment" -ForegroundColor Gray
    Write-Host "  .\docker-build.ps1 -BuildOnly -NoCache               # Build only with no cache" -ForegroundColor Gray
}

# Show help if requested
if ($Help) {
    Show-Usage
    exit 0
}

Write-Host "🐳 Flask Chat Server Docker Build Script" -ForegroundColor Blue
Write-Host "=========================================" -ForegroundColor Blue
Write-Host "Environment: $Environment" -ForegroundColor Yellow
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
    # Build based on environment
    if ($Environment -eq "development") {
        Write-Host "🔧 Building development environment..." -ForegroundColor Green
        
        # Build development image
        Write-Host "Building development image..." -ForegroundColor Blue
        $dockerCmd = "docker build " + ($BuildArgs -join " ") + " -f Dockerfile.dev -t transcribe-chat:dev ."
        Invoke-Expression $dockerCmd
        
        if (-not $BuildOnly) {
            Write-Host "Starting development environment..." -ForegroundColor Blue
            docker-compose -f docker-compose.chat.yml up -d chat-server
            
            Write-Host "✅ Development environment started!" -ForegroundColor Green
            Write-Host "📊 Chat Server: http://localhost:5000" -ForegroundColor Yellow
            Write-Host "🏥 Health Check: http://localhost:5000/health" -ForegroundColor Yellow
            Write-Host ""
            Write-Host "To view logs: docker-compose -f docker-compose.chat.yml logs -f chat-server" -ForegroundColor Blue
            Write-Host "To stop: docker-compose -f docker-compose.chat.yml down" -ForegroundColor Blue
        }
        
    } elseif ($Environment -eq "production") {
        Write-Host "🚀 Building production environment..." -ForegroundColor Green
        
        # Build production image
        Write-Host "Building production image..." -ForegroundColor Blue
        $dockerCmd = "docker build " + ($BuildArgs -join " ") + " -f Dockerfile.production -t transcribe-chat:prod ."
        Invoke-Expression $dockerCmd
        
        if (-not $BuildOnly) {
            Write-Host "Starting production environment..." -ForegroundColor Blue
            docker-compose -f docker-compose.chat.yml --profile production up -d chat-server-prod
            
            Write-Host "✅ Production environment started!" -ForegroundColor Green
            Write-Host "📊 Chat Server: http://localhost:5001" -ForegroundColor Yellow
            Write-Host "🏥 Health Check: http://localhost:5001/health" -ForegroundColor Yellow
            Write-Host ""
            Write-Host "To view logs: docker-compose -f docker-compose.chat.yml logs -f chat-server-prod" -ForegroundColor Blue
            Write-Host "To stop: docker-compose -f docker-compose.chat.yml --profile production down" -ForegroundColor Blue
        }
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
