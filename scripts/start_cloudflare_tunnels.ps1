<#
.SYNOPSIS
  Starts the Cloudflare Quick Tunnels that expose this host's OpenAgent stack
  (frontend, api, ZITADEL) to the internet, for the no-owned-domain deploy
  path documented in docs/deployment-runbook.md.

.DESCRIPTION
  Quick Tunnels have no persistent identity: every time cloudflared starts,
  Cloudflare hands it a brand-new random *.trycloudflare.com hostname. That
  means restarting this script (including via the scheduled task that runs
  it at logon) always produces NEW public URLs - after it runs, re-read the
  hostnames from the log files below and update:
    - .env (OPENAGENT_APP_DOMAIN / OPENAGENT_API_DOMAIN / OPENAGENT_AUTH_DOMAIN /
      ZITADEL_DOMAIN / NEXT_PUBLIC_API_BASE_URL / OPENAGENT_ZITADEL_ISSUER_URL /
      OPENAGENT_ZITADEL_REDIRECT_URI / OPENAGENT_ZITADEL_POST_LOGOUT_REDIRECT_URI /
      OPENAGENT_CORS_ORIGINS)
    - the ZITADEL console's "OpenAgent Web" app Redirect Settings (add the new
      app-domain callback URL; the old ones can stay registered)
  then `docker compose up -d --force-recreate api worker frontend zitadel-api
  zitadel-login zitadel-proxy` to pick up the new .env.

  This is the accepted tradeoff of the free Quick Tunnel tier - moving to a
  Named Tunnel on an owned domain removes this step entirely by giving each
  service a fixed hostname.

.NOTES
  Registered to run at user logon via:
    schtasks /Create /TN "OpenAgent Cloudflare Tunnels" /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -File <this path>" /SC ONLOGON /RL LIMITED /F
#>

$cloudflared = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
$logDir = "$PSScriptRoot\..\.cloudflared-logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$targets = @(
    @{ Name = "frontend"; Port = 3000 },
    @{ Name = "api";      Port = 8000 },
    @{ Name = "auth";     Port = 80 }
)

foreach ($t in $targets) {
    $logFile = Join-Path $logDir "tunnel-$($t.Name).log"
    Start-Process -FilePath $cloudflared `
        -ArgumentList "tunnel --url http://localhost:$($t.Port)" `
        -RedirectStandardError $logFile `
        -WindowStyle Hidden
}

Start-Sleep -Seconds 6
foreach ($t in $targets) {
    $logFile = Join-Path $logDir "tunnel-$($t.Name).log"
    $url = Select-String -Path $logFile -Pattern "https://[a-z0-9-]*\.trycloudflare\.com" |
        Select-Object -First 1 | ForEach-Object { $_.Matches[0].Value }
    Write-Host "$($t.Name): $url"
}
