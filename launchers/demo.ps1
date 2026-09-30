<#
.SYNOPSIS
    Builds and starts the stack and opens a public Cloudflare Quick Tunnel to it.
.PARAMETER DemoPeers
    Also start the scripted cast (Alice, Bob, Mallory and swarm peers in room "demo").
    Without it the network starts empty: people join with any name, create their own room,
    and other nodes join that room.
#>
param([switch]$DemoPeers)

$ErrorActionPreference = "Stop"

function Invoke-DockerComposeToHost {
    param([Parameter(Mandatory)][string[]]$Arguments)

    $savedErrorActionPreference = $ErrorActionPreference
    $hasNativePreference = Test-Path Variable:PSNativeCommandUseErrorActionPreference
    if ($hasNativePreference) {
        $savedNativePreference = $PSNativeCommandUseErrorActionPreference
    }

    try {
        # Docker writes progress to stderr on some versions. Keep it visible,
        # but determine success only from the process exit code.
        $ErrorActionPreference = "Continue"
        if ($hasNativePreference) {
            $PSNativeCommandUseErrorActionPreference = $false
        }
        & docker compose @Arguments
        $script:DockerComposeExitCode = $LASTEXITCODE
        $script:DockerComposeInvocationError = $null
    }
    catch {
        $script:DockerComposeExitCode = 1
        $script:DockerComposeInvocationError = $_
    }
    finally {
        $ErrorActionPreference = $savedErrorActionPreference
        if ($hasNativePreference) {
            $PSNativeCommandUseErrorActionPreference = $savedNativePreference
        }
    }
}

function Show-DockerDiagnostics {
    param([string]$Reason)

    Write-Host ""
    Write-Host $Reason -ForegroundColor Red
    Write-Host "Docker Compose service status:" -ForegroundColor Yellow
    Invoke-DockerComposeToHost -Arguments @("ps", "-a")
    Write-Host "Recent cloudflared logs:" -ForegroundColor Yellow
    Invoke-DockerComposeToHost -Arguments @("logs", "--no-color", "--tail=100", "cloudflared")
}

function Start-DemoUrlWindow {
    param([Parameter(Mandatory)][string]$Url)

    $shell = Get-Command pwsh.exe -ErrorAction SilentlyContinue
    if (-not $shell) {
        $shell = Get-Command powershell.exe -ErrorAction Stop
    }

    $tempDirectory = Join-Path ([System.IO.Path]::GetTempPath()) ("BlockchainSimulationDemo-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $tempDirectory -Force | Out-Null
    $urlFile = Join-Path $tempDirectory "public-url.txt"
    $displayScript = Join-Path $tempDirectory "show-demo-url.ps1"
    [System.IO.File]::WriteAllText($urlFile, $Url, [System.Text.UTF8Encoding]::new($false))

    $displayScriptContent = @'
$publicUrl = [System.IO.File]::ReadAllText((Join-Path $PSScriptRoot "public-url.txt")).Trim()
Write-Host ""
Write-Host "================================================" -ForegroundColor Green
Write-Host "             BLOCKCHAIN SIMULATION" -ForegroundColor Green
Write-Host "                  DEMO LIVE" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green
Write-Host ""
Write-Host "PUBLIC DEMO URL:" -ForegroundColor Yellow
Write-Host $publicUrl
Write-Host ""
Write-Host "Ctrl+Click the URL above to open the demo." -ForegroundColor Cyan
Write-Host "This window only displays the URL; close it when finished." -ForegroundColor DarkGray
'@
    [System.IO.File]::WriteAllText($displayScript, $displayScriptContent, [System.Text.UTF8Encoding]::new($false))

    $windowsTerminal = Get-Command wt.exe -ErrorAction SilentlyContinue
    if ($windowsTerminal) {
        try {
            $wtArguments = '-w new "{0}" -NoExit -File "{1}"' -f $shell.Source, $displayScript
            Start-Process -FilePath $windowsTerminal.Source -ArgumentList $wtArguments -ErrorAction Stop | Out-Null
            $script:DemoUrlWindowTempDirectory = $tempDirectory
            return "Windows Terminal"
        }
        catch {
            Write-Warning "Could not open Windows Terminal; opening a PowerShell window instead. $($_.Exception.Message)"
        }
    }

    $shellArguments = '-NoExit -File "{0}"' -f $displayScript
    Start-Process -FilePath $shell.Source -ArgumentList $shellArguments -ErrorAction Stop | Out-Null
    $script:DemoUrlWindowTempDirectory = $tempDirectory
    return "PowerShell"
}

Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    Write-Host "Building and starting the Docker Compose stack; waiting for services to become ready..." -ForegroundColor Cyan
    $ProfileArgs = if ($DemoPeers) { @("--profile", "demo") } else { @() }
    if (-not $DemoPeers) {
        # Leftover demo peers from an earlier run would still be sitting in room "demo".
        Invoke-DockerComposeToHost -Arguments @("--profile", "demo", "rm", "-sf", "peer-alice", "peer-bob", "peer-mallory", "peer-swarm")
    }
    Invoke-DockerComposeToHost -Arguments ($ProfileArgs + @("up", "-d", "--build", "--wait", "--wait-timeout", "90"))
    if ($script:DockerComposeExitCode -ne 0) {
        $reason = "ERROR: Docker Compose failed to build or start the application (exit code $script:DockerComposeExitCode)."
        if ($script:DockerComposeInvocationError) {
            $reason += "`n$($script:DockerComposeInvocationError)"
        }
        Show-DockerDiagnostics -Reason $reason
        exit $script:DockerComposeExitCode
    }

    Write-Host "Services are running. Waiting up to 90 seconds for the Cloudflare Quick Tunnel URL..." -ForegroundColor Cyan
    $deadline = [DateTime]::UtcNow.AddSeconds(90)
    $publicUrl = $null
    $lastLogReadError = $null

    while ([DateTime]::UtcNow -lt $deadline) {
        $savedErrorActionPreference = $ErrorActionPreference
        $hasNativePreference = Test-Path Variable:PSNativeCommandUseErrorActionPreference
        if ($hasNativePreference) {
            $savedNativePreference = $PSNativeCommandUseErrorActionPreference
        }
        try {
            $ErrorActionPreference = "Continue"
            if ($hasNativePreference) {
                $PSNativeCommandUseErrorActionPreference = $false
            }
            $cloudflaredLogs = @(& docker compose logs --no-color --tail=300 cloudflared 2>&1)
            $logsExitCode = $LASTEXITCODE
            if ($logsExitCode -eq 0) {
                $lastLogReadError = $null
            }
            elseif ($cloudflaredLogs.Count -gt 0) {
                $lastLogReadError = $cloudflaredLogs -join "`n"
            }
        }
        catch {
            $logsExitCode = 1
            $lastLogReadError = $_
            $cloudflaredLogs = @()
        }
        finally {
            $ErrorActionPreference = $savedErrorActionPreference
            if ($hasNativePreference) {
                $PSNativeCommandUseErrorActionPreference = $savedNativePreference
            }
        }

        if ($logsExitCode -eq 0) {
            $logText = $cloudflaredLogs -join "`n"
            $matches = [regex]::Matches(
                $logText,
                'https?://[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?\.trycloudflare\.com',
                [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
            )
            if ($matches.Count -gt 0) {
                $publicUrl = $matches[$matches.Count - 1].Value.TrimEnd('.', ',', ';', ')', ']', '}', '"', "'")
                break
            }
        }

        Start-Sleep -Seconds 2
    }

    if (-not $publicUrl) {
        $reason = "ERROR: cloudflared did not produce a trycloudflare.com URL within 90 seconds."
        if ($lastLogReadError) {
            $reason += "`nCould not read cloudflared logs: $lastLogReadError"
        }
        Show-DockerDiagnostics -Reason $reason
        exit 1
    }

    try {
        $displayTerminal = Start-DemoUrlWindow -Url $publicUrl
        Write-Host "Opened the demo URL in a separate $displayTerminal window." -ForegroundColor Cyan
    }
    catch {
        Write-Warning "Could not open a separate URL window: $($_.Exception.Message)"
    }

    Write-Host ""
    Write-Host "================================================" -ForegroundColor Green
    Write-Host "                 DEMO LIVE" -ForegroundColor Green
    Write-Host "================================================" -ForegroundColor Green
    Write-Host "PUBLIC DEMO URL" -ForegroundColor Yellow
    Write-Host $publicUrl
    try {
        Set-Clipboard -Value $publicUrl
        Write-Host "(Also copied to clipboard.)" -ForegroundColor DarkGray
    }
    catch {
        # The printed URL is the primary way to open the demo; clipboard
        # support is optional in some PowerShell hosts.
    }
    Write-Host ""
    Write-Host "Following Docker Compose logs. Press Ctrl+C to detach; containers will keep running." -ForegroundColor Cyan
    Invoke-DockerComposeToHost -Arguments ($ProfileArgs + @("logs", "--follow", "--tail=20"))
    Write-Host "Detached from Compose logs. Docker containers remain running." -ForegroundColor Cyan
}
finally {
    Pop-Location
    if ($script:DemoUrlWindowTempDirectory -and (Test-Path -LiteralPath $script:DemoUrlWindowTempDirectory)) {
        Remove-Item -LiteralPath $script:DemoUrlWindowTempDirectory -Recurse -Force -ErrorAction SilentlyContinue
    }
}
