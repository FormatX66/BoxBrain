$ErrorActionPreference='Stop'
$Controller='https://arkmatx.com/aurum/index.php'
$Portal='https://aurum.arkmatx.com'
$Root=if($env:AURUM_HOME){$env:AURUM_HOME}else{Join-Path $env:USERPROFILE '.aurum'}
New-Item -ItemType Directory -Path $Root -Force | Out-Null
$hostName=$env:COMPUTERNAME
$os=[System.Environment]::OSVersion.VersionString
$arch=$env:PROCESSOR_ARCHITECTURE
$seed="$hostName|$os|$arch"
$sha=[Security.Cryptography.SHA256]::Create()
try{$nodeId=([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($seed))).Replace('-','').ToLowerInvariant()).Substring(0,16)}finally{$sha.Dispose()}
$config=[ordered]@{schema='aurum.node.v0';node_id=$nodeId;name=$hostName;controller=$Controller;portal=$Portal;carrier='https-outbound';os=$os;arch=$arch}
$config | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $Root 'node.json') -Encoding UTF8
$now=[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$enroll=[ordered]@{schema='aurum.uaf.v0';frame_id="enroll-$nodeId-$now";origin="Aurum-Node-$nodeId";target='Aurum-Arkmatx';intent='node_enroll';state_delta=@{node_id=$nodeId;name=$hostName;os=$os;arch=$arch;carrier='https-outbound'};provenance=@{node="Aurum-Node-$nodeId";created=$now};verification=@{content_addressed=$true;reversible=$true}}
$response=Invoke-RestMethod -Method Post -Uri $Controller -ContentType 'application/json' -Body ($enroll|ConvertTo-Json -Depth 8 -Compress)
$response | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $Root 'enrollment.json') -Encoding UTF8
$now=[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$heartbeat=[ordered]@{schema='aurum.uaf.v0';frame_id="heartbeat-$nodeId-$now";origin="Aurum-Node-$nodeId";target='Aurum-Arkmatx';intent='node_heartbeat';state_delta=@{node_id=$nodeId;carrier='https-outbound'};provenance=@{node="Aurum-Node-$nodeId";created=$now};verification=@{content_addressed=$true;reversible=$true}}
$beatResponse=Invoke-RestMethod -Method Post -Uri $Controller -ContentType 'application/json' -Body ($heartbeat|ConvertTo-Json -Depth 8 -Compress)
$beatResponse | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $Root 'heartbeat.json') -Encoding UTF8
Write-Host "Aurum node enrolled and heartbeat confirmed."
Write-Host "Node: $nodeId"
Write-Host "Controller: $Controller"
Write-Host "Config: $(Join-Path $Root 'node.json')"
