$ErrorActionPreference='Stop'
$Root=if($env:AURUM_HOME){$env:AURUM_HOME}else{Join-Path $env:USERPROFILE '.aurum'}
$ConfigPath=Join-Path $Root 'node.json'
$WorkerPath=Join-Path $Root 'worker.ps1'
$LogPath=Join-Path $Root 'watchdog.log'
$DefaultController='https://arkmatx.com/aurum/index.php'

New-Item -ItemType Directory -Path $Root -Force | Out-Null

function Log($m){
  try{Add-Content -LiteralPath $LogPath -Value ("{0:o} {1}" -f [DateTimeOffset]::UtcNow,$m)}catch{}
}

function Ensure-Worker {
  if(-not (Test-Path -LiteralPath $WorkerPath -PathType Leaf)){
    Log 'worker-file-missing'
    return
  }
  $existing=@(Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
    Where-Object {$_.CommandLine -like "*$WorkerPath*"})
  if($existing.Count -eq 0){
    Start-Process powershell.exe -WindowStyle Hidden -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',$WorkerPath)
    Log 'worker-restarted'
  }
}

function Send-Heartbeat {
  if(-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)){return}
  $cfg=Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
  if(-not $cfg.node_id){return}
  $controller=if($cfg.controller){[string]$cfg.controller}else{$DefaultController}
  $now=[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
  $heartbeat=[ordered]@{
    schema='aurum.uaf.v0'
    frame_id="heartbeat-$($cfg.node_id)-$now-watchdog"
    origin="Aurum-Node-$($cfg.node_id)"
    target='Aurum-Arkmatx'
    intent='node_heartbeat'
    state_delta=@{node_id=[string]$cfg.node_id;carrier='https-outbound';watchdog=$true}
    provenance=@{node="Aurum-Node-$($cfg.node_id)";created=$now}
    verification=@{content_addressed=$true;reversible=$true}
  }
  Invoke-RestMethod -Method Post -Uri $controller -ContentType 'application/json' -Body ($heartbeat|ConvertTo-Json -Depth 8 -Compress) -TimeoutSec 20 | Out-Null
  Log "heartbeat node=$($cfg.node_id)"
}

while($true){
  try{Ensure-Worker}catch{Log "worker-check-error $($_.Exception.Message)"}
  try{Send-Heartbeat}catch{Log "heartbeat-error $($_.Exception.Message)"}
  Start-Sleep -Seconds 60
}
