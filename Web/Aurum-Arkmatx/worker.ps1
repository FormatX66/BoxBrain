$ErrorActionPreference='Stop'
$Controller='https://arkmatx.com/aurum/index.php'
$Root=if($env:AURUM_HOME){$env:AURUM_HOME}else{Join-Path $env:USERPROFILE '.aurum'}
$ConfigPath=Join-Path $Root 'node.json'
$LogPath=Join-Path $Root 'worker.log'
$KeyPath=Join-Path $HOME '.ssh\boxbrain_pi_ed25519'
function Log($m){Add-Content -LiteralPath $LogPath -Value ("{0:o} {1}" -f [DateTimeOffset]::UtcNow,$m)}
function Post-Result($nodeId,$workId,$status,$detail){
  $body=[ordered]@{node_id=$nodeId;work_id=$workId;status=$status;detail=$detail;completed_at=[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()}
  try{Invoke-RestMethod -Method Post -Uri "$Controller/work/result" -ContentType 'application/json' -Body ($body|ConvertTo-Json -Depth 10 -Compress)|Out-Null}catch{Log "result-post-failed $($_.Exception.Message)"}
}
function Probe-Tcp($address,$port){
  try{return [bool](Test-NetConnection -ComputerName $address -Port $port -InformationLevel Quiet -WarningAction SilentlyContinue)}catch{return $false}
}
function Invoke-BBPI4Bootstrap($nodeId,$work){
  $addresses=@('10.12.194.1','10.42.194.1','bbpi4.local','192.168.0.194')
  if($work.payload.addresses){$addresses=@($work.payload.addresses)}
  $ssh=(Get-Command ssh.exe -ErrorAction SilentlyContinue | Select-Object -First 1)
  $keyPresent=Test-Path -LiteralPath $KeyPath -PathType Leaf
  $observations=@()
  foreach($address in $addresses){
    $obs=[ordered]@{address=$address;icmp=$false;ssh22=$false;http80=$false;https443=$false;ssh_attempted=$false;ssh_exit=$null}
    try{$obs.icmp=[bool](Test-Connection -ComputerName $address -Count 1 -Quiet -ErrorAction SilentlyContinue)}catch{}
    $obs.ssh22=Probe-Tcp $address 22
    $obs.http80=Probe-Tcp $address 80
    $obs.https443=Probe-Tcp $address 443
    if($obs.ssh22 -and $ssh -and $keyPresent){
      $obs.ssh_attempted=$true
      $args=@('-i',$KeyPath,'-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','ConnectTimeout=5','-o','StrictHostKeyChecking=accept-new',"kali@$address",'curl -fsSL https://aurum.arkmatx.com/bootstrap.sh | sh')
      $output=& $ssh.Source @args 2>&1
      $code=$LASTEXITCODE
      $obs.ssh_exit=$code
      $observations += [pscustomobject]$obs
      if($code -eq 0){return @{status='completed';detail=@{address=$address;carrier='ssh';node_id=$nodeId;observations=$observations;output=(@($output|Select-Object -Last 12)-join "`n")}}}
      Log "bbpi4 ssh failed address=$address code=$code"
      continue
    }
    $observations += [pscustomobject]$obs
  }
  $reason=if(-not $ssh){'ssh-client-unavailable'}elseif(-not $keyPresent){'authorized-pi-key-missing'}else{'no-authorized-bbpi4-ssh-route'}
  return @{status='failed';detail=@{reason=$reason;key=$KeyPath;node_id=$nodeId;observations=$observations;safe_carriers_tried=@('icmp','tcp22','tcp80','tcp443','ssh')}}
}
while($true){
  try{
    if(-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)){Start-Sleep -Seconds 5;continue}
    $cfg=Get-Content -LiteralPath $ConfigPath -Raw|ConvertFrom-Json
    $nodeId=[string]$cfg.node_id
    $lease=Invoke-RestMethod -Method Get -Uri "$Controller/work/lease?node_id=$([uri]::EscapeDataString($nodeId))&capabilities=bbpi4-bootstrap" -TimeoutSec 20
    if($lease.work){
      $work=$lease.work
      Log "leased $($work.work_id) capability=$($work.capability)"
      if([string]$work.capability -eq 'bbpi4-bootstrap'){$r=Invoke-BBPI4Bootstrap $nodeId $work}else{$r=@{status='rejected';detail=@{reason='capability-not-allowlisted'}}}
      Post-Result $nodeId ([string]$work.work_id) ([string]$r.status) $r.detail
    }
  }catch{Log "cycle-error $($_.Exception.Message)"}
  Start-Sleep -Seconds 8
}
