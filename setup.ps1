<#
.SYNOPSIS
    One-time setup: configure Vibe-Trading agent env vars + create crypto_research table.
.DESCRIPTION
    1. Adds SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY to agent/.env
    2. Opens Supabase SQL Editor so you can create the crypto_research table
    3. Validates the setup by querying Supabase REST API
#>

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$AgentEnv = Join-Path $ProjectRoot "agent" ".env"
$MigrationSql = Join-Path $PSScriptRoot "supabase_migration.sql"
$SupabaseUrl = "https://ymnlqggxeeyqvrojsrzh.supabase.co"

Write-Host "╔══════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║   Vibe-Trading → Crypto Dashboard Integration   ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# ── Step 1: Agent .env file ──────────────────────────────────────────
Write-Host "── Step 1: Agent environment variables ──" -ForegroundColor Yellow

# Read existing .env or start fresh
$envContent = if (Test-Path $AgentEnv) { Get-Content $AgentEnv -Raw } else { "" }

# Check if SUPABASE vars already exist
$hasUrl = $envContent -match "^\s*SUPABASE_URL="
$hasKey = $envContent -match "^\s*SUPABASE_SERVICE_ROLE_KEY="

if ($hasUrl -and $hasKey) {
    Write-Host "  ✓ SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY already set in agent/.env" -ForegroundColor Green
} else {
    # Working service_role key (verified: read+write both pass)
    $defaultKey = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InltbmxxZ2d4ZWV5cXZyb2pzcnpoIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4Mzc2NDY0NCwiZXhwIjoyMDk5MzQwNjQ0fQ.rynI0deIhDdOWfSujtDX0_KyZxGEv2iMT32SIz4DlQw"
    $serviceKey = Read-Host "Enter your Supabase service_role key [Enter to use verified key]"
    if (-not $serviceKey) { $serviceKey = $defaultKey }
    # Replace existing lines or append
    if ($hasUrl) {
        $envContent = $envContent -replace '^\s*SUPABASE_URL=.*', "SUPABASE_URL=$SupabaseUrl"
    } else {
        $envContent += "`nSUPABASE_URL=$SupabaseUrl`n"
    }
    if ($hasKey) {
        $envContent = $envContent -replace '^\s*SUPABASE_SERVICE_ROLE_KEY=.*', "SUPABASE_SERVICE_ROLE_KEY=$serviceKey"
    } else {
        $envContent += "SUPABASE_SERVICE_ROLE_KEY=$serviceKey`n"
    }
    Set-Content -Path $AgentEnv -Value $envContent -NoNewline
    Write-Host "  ✓ Written SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY to agent/.env" -ForegroundColor Green
}

Write-Host ""

# ── Step 2: Create the crypto_research table ─────────────────────────
Write-Host "── Step 2: Create crypto_research table ──" -ForegroundColor Yellow

# Check if table already exists by querying Supabase REST API
$anonKey = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InltbmxxZ2d4ZWV5cXZyb2pzcnpoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODM3NjQ2NDQsImV4cCI6MjA5OTM0MDY0NH0.wsO53Ninsb_9Mxt0Me5q3vYuQMr5XFUASYgdBzeHfbQ"

try {
    $response = Invoke-RestMethod -Uri "${SupabaseUrl}/rest/v1/crypto_research?select=count&limit=0" `
        -Headers @{ apikey = $anonKey; Authorization = "Bearer $anonKey" } `
        -Method Get -ErrorAction Stop
    Write-Host "  ✓ crypto_research table already exists (query succeeded)" -ForegroundColor Green
} catch {
    # Table likely doesn't exist. Offer to open SQL Editor or try Management API.
    Write-Host "  ! crypto_research table not found yet." -ForegroundColor Yellow
    Write-Host ""

    # Try Management API if user provides a PAT
    $pat = Read-Host "Enter Supabase PAT (Personal Access Token) to auto-run the migration [Enter to skip]"
    if ($pat) {
        $projectRef = "ymnlqggxeeyqvrojsrzh"
        $migrationSql = Get-Content $MigrationSql -Raw
        try {
            $result = Invoke-RestMethod -Uri "https://api.supabase.com/v1/projects/$projectRef/sql" `
                -Headers @{ Authorization = "Bearer $pat"; "Content-Type" = "application/json" } `
                -Body (@{ query = $migrationSql } | ConvertTo-Json) `
                -Method Post -ErrorAction Stop
            Write-Host "  ✓ Migration SQL executed successfully!" -ForegroundColor Green
        } catch {
            Write-Host "  ✗ Management API call failed: $_" -ForegroundColor Red
            Write-Host "    Falling through to manual step..." -ForegroundColor DarkYellow
            $pat = $null
        }
    }

    if (-not $pat) {
        # Open the Supabase SQL Editor in browser
        $sqlEditorUrl = "https://supabase.com/dashboard/project/ymnlqggxeeyqvrojsrzh/sql/new"
        Write-Host "  ┌───────────────────────────────────────────────────────────┐" -ForegroundColor DarkCyan
        Write-Host "  │ Open this URL in your browser:                            │" -ForegroundColor DarkCyan
        Write-Host "  │ $sqlEditorUrl │" -ForegroundColor DarkCyan
        Write-Host "  │                                                           │" -ForegroundColor DarkCyan
        Write-Host "  │ Copy and paste the contents of this file into the editor: │" -ForegroundColor DarkCyan
        Write-Host "  │   $MigrationSql │" -ForegroundColor DarkCyan
        Write-Host "  │                                                           │" -ForegroundColor DarkCyan
        Write-Host "  │ Then click RUN — one-time setup, takes 2 seconds.         │" -ForegroundColor DarkCyan
        Write-Host "  └───────────────────────────────────────────────────────────┘" -ForegroundColor DarkCyan

        $choice = Read-Host "Open the SQL Editor in your browser now? (Y/n)"
        if ($choice -ne "n") {
            Start-Process $sqlEditorUrl
            Write-Host "  → Browser opened. Paste the SQL from supabase_migration.sql and click RUN." -ForegroundColor Green
        }

        # Also show the SQL inline
        Write-Host ""
        Write-Host "  SQL to run (copied below for convenience):" -ForegroundColor DarkGray
        Get-Content $MigrationSql | ForEach-Object { Write-Host "  | $_" -ForegroundColor DarkGray }
    }

    Write-Host ""
    $completed = Read-Host "Press Enter after you've run the SQL (or type 'skip' to skip validation)"
    if ($completed -eq "skip") {
        Write-Host "  ! Skipping validation." -ForegroundColor DarkYellow
    } else {
        # Verify
        try {
            $response = Invoke-RestMethod -Uri "${SupabaseUrl}/rest/v1/crypto_research?select=count&limit=0" `
                -Headers @{ apikey = $anonKey; Authorization = "Bearer $anonKey" } `
                -Method Get -ErrorAction Stop
            Write-Host "  ✓ crypto_research table verified!" -ForegroundColor Green
        } catch {
            Write-Host "  ✗ Table still not reachable. Check the Supabase SQL Editor for errors." -ForegroundColor Red
        }
    }
}

Write-Host ""

# ── Step 3: Validate existing data ───────────────────────────────────
Write-Host "── Step 3: Validate Supabase connectivity ──" -ForegroundColor Yellow

try {
    $dataResponse = Invoke-RestMethod -Uri "${SupabaseUrl}/rest/v1/crypto_data?select=symbol,current_price&limit=5" `
        -Headers @{ apikey = $anonKey; Authorization = "Bearer $anonKey" } `
        -Method Get -ErrorAction Stop
    Write-Host "  ✓ Supabase accessible. ${SupabaseUrl}" -ForegroundColor Green
    Write-Host "  ✓ crypto_data has data ($($dataResponse.Count) samples)" -ForegroundColor Green
} catch {
    Write-Host "  ! Could not reach Supabase: $_" -ForegroundColor Red
    Write-Host "    Check your internet connection and project URL." -ForegroundColor DarkYellow
}

Write-Host ""

# ── Summary ───────────────────────────────────────────────────────────
Write-Host "╔══════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║                   Next Steps                     ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""
Write-Host "  1. Start Vibe-Trading with the new env vars:"
Write-Host "     cd $ProjectRoot"
Write-Host "     python main.py"
Write-Host ""
Write-Host "  2. Open the crypto dashboard:"
Write-Host "     file://$PSScriptRoot/index.html"
Write-Host "     (or push this repo to GitHub Pages — see the Deploy Dashboard workflow)"
Write-Host ""
Write-Host "  3. Ask the agent to research a symbol:"
Write-Host '     "Research BTC-USD: technical analysis, sentiment, and key levels"'
Write-Host ""
Write-Host "  4. Watch the result appear in the AI Research panel on the dashboard!"
Write-Host ""
