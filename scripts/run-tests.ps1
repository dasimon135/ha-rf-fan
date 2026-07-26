<#
.SYNOPSIS
    Run the whole test suite (including the Home Assistant tests) in Docker.

.DESCRIPTION
    Home Assistant's runner imports the POSIX-only `fcntl`, so
    pytest-homeassistant-custom-component cannot run on Windows natively — the
    HA-dependent modules just skip themselves there and only the pure suite runs.
    This container gives the same Linux + Python 3.14 environment as CI.

    Rebuild the image (-Rebuild) after changing requirements-test.txt.

.EXAMPLE
    .\scripts\run-tests.ps1
    .\scripts\run-tests.ps1 tests/test_actions.py -q
    .\scripts\run-tests.ps1 -Rebuild
#>
[CmdletBinding()]
param(
    [switch]$Rebuild,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PytestArgs
)

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$image = 'rf-fan-tests'

$exists = $null -ne (docker image ls -q $image)
if ($Rebuild -or -not $exists) {
    Write-Host "Building $image ..."
    docker build -q -f (Join-Path $repo 'scripts/Dockerfile.tests') -t $image $repo
}

if (-not $PytestArgs) { $PytestArgs = @('tests/', '-q') }

docker run --rm -v "${repo}:/app" -w /app $image python -m pytest @PytestArgs
