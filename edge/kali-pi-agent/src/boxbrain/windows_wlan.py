"""Structured Windows WLAN inventory through supported Windows commands.

The collector deliberately never asks Windows for ``key=clear`` and never reads
protected WLAN profile files.  It returns only profile metadata and a boolean
``credential_available`` signal derived from the normal profile summary.
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


WLAN_RECONNECT_AUTHORIZATION = "I am authorized to reconnect this Windows WLAN profile"
WLAN_RECONNECT_CONFIRMATION = "RECONNECT WINDOWS WLAN"
_ACTIONS = {"interfaces", "profiles", "status", "diagnose", "reconnect"}


class WindowsWlanError(RuntimeError):
    """Raised when structured Windows WLAN collection fails."""


_POWERSHELL = r"""
$ErrorActionPreference = 'Stop'
$request = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('__REQUEST__')) | ConvertFrom-Json

function Invoke-BoxBrainNetsh {
    param([string[]]$Arguments)
    $output = @(& "$env:SystemRoot\System32\netsh.exe" @Arguments 2>&1)
    if ($LASTEXITCODE -ne 0) { throw ($output -join "`n") }
    return $output
}

function Convert-BoxBrainNetshBlocks {
    param([object[]]$Lines)
    $blocks = [Collections.Generic.List[object]]::new()
    $current = [ordered]@{}
    foreach ($line in $Lines) {
        $text = [string]$line
        if ($text -notmatch '^\s*([^:]+?)\s*:\s*(.*?)\s*$') { continue }
        $key = $Matches[1].Trim()
        $value = $Matches[2].Trim()
        if ($key -eq 'Name' -and $current.Contains('Name')) {
            $blocks.Add([pscustomobject]$current)
            $current = [ordered]@{}
        }
        $current[$key] = $value
    }
    if ($current.Count -gt 0) { $blocks.Add([pscustomobject]$current) }
    return @($blocks)
}

function Get-BoxBrainValue {
    param([object]$Block, [string[]]$Names)
    foreach ($name in $Names) {
        $property = $Block.PSObject.Properties[$name]
        if ($null -ne $property) { return [string]$property.Value }
    }
    return $null
}

function Get-BoxBrainInventory {
    $netshBlocks = Convert-BoxBrainNetshBlocks (Invoke-BoxBrainNetsh @('wlan','show','interfaces'))
    $adapters = @()
    try {
        $adapters = @(
            Get-NetAdapter -Physical -IncludeHidden -ErrorAction Stop |
                Where-Object {
                    $_.HardwareInterface -eq $true -and (
                        ([string]$_.NdisPhysicalMedium) -match '802\.11|Wireless' -or
                        ([string]$_.InterfaceDescription) -match 'Wi-?Fi|Wireless|802\.11'
                    )
                }
        )
    } catch {
        $adapters = @()
    }
    if ($adapters.Count -eq 0) {
        $adapters = @(
            $netshBlocks |
                Where-Object { Get-BoxBrainValue $_ @('Name') } |
                ForEach-Object {
                    [pscustomobject]@{
                        Name = Get-BoxBrainValue $_ @('Name')
                        InterfaceGuid = Get-BoxBrainValue $_ @('GUID')
                        InterfaceDescription = Get-BoxBrainValue $_ @('Description')
                        ifIndex = $null
                    }
                }
        )
    }
    $interfaces = [Collections.Generic.List[object]]::new()
    $profiles = [Collections.Generic.List[object]]::new()
    foreach ($adapter in $adapters) {
        $name = [string]$adapter.Name
        $block = @($netshBlocks | Where-Object { (Get-BoxBrainValue $_ @('Name')) -eq $name } | Select-Object -First 1)
        $netsh = if ($block.Count) { $block[0] } else { [pscustomobject]@{} }
        $ipConfig = @()
        $dnsConfig = @()
        try {
            $ipConfig = @(Get-NetIPConfiguration -InterfaceAlias $name -ErrorAction Stop)
        } catch {
            $ipConfig = @()
        }
        try {
            $dnsConfig = @(Get-DnsClientServerAddress -InterfaceAlias $name -ErrorAction Stop)
        } catch {
            $dnsConfig = @()
        }
        $signalText = Get-BoxBrainValue $netsh @('Signal')
        $signal = $null
        if ($signalText -match '(\d+)') { $signal = [int]$Matches[1] }
        $guid = ([string]$adapter.InterfaceGuid).Trim('{}')
        if (-not $guid) { $guid = Get-BoxBrainValue $netsh @('GUID') }
        $description = [string]$adapter.InterfaceDescription
        if (-not $description) { $description = Get-BoxBrainValue $netsh @('Description') }
        $interfaces.Add([ordered]@{
            name = $name
            guid = $guid
            description = $description
            state = (Get-BoxBrainValue $netsh @('State'))
            current_ssid = (Get-BoxBrainValue $netsh @('SSID'))
            profile = (Get-BoxBrainValue $netsh @('Profile'))
            signal_percent = $signal
            authentication = (Get-BoxBrainValue $netsh @('Authentication'))
            encryption = (Get-BoxBrainValue $netsh @('Cipher'))
            ipv4 = @($ipConfig.IPv4Address | ForEach-Object { [string]$_.IPAddress })
            gateway = @($ipConfig.IPv4DefaultGateway | ForEach-Object { [string]$_.NextHop })
            dns = @($dnsConfig.ServerAddresses | ForEach-Object { [string]$_ })
        })

        $priority = 0
        $profileLines = Invoke-BoxBrainNetsh @('wlan','show','profiles',"interface=$name")
        foreach ($line in $profileLines) {
            if ([string]$line -notmatch '^\s*(?:All User Profile|Current User Profile)\s*:\s*(.+?)\s*$') { continue }
            $profileName = $Matches[1].Trim()
            $priority++
            $detailBlocks = @(
                Convert-BoxBrainNetshBlocks (
                    Invoke-BoxBrainNetsh @('wlan','show','profile',"name=$profileName","interface=$name")
                )
            )
            $matchingDetails = @(
                $detailBlocks |
                    Where-Object { (Get-BoxBrainValue $_ @('Name')) -ceq $profileName } |
                    Select-Object -First 1
            )
            $detail = if ($matchingDetails.Count) {
                $matchingDetails[0]
            } elseif ($detailBlocks.Count) {
                $detailBlocks[0]
            } else {
                [pscustomobject]@{}
            }
            $mode = Get-BoxBrainValue $detail @('Connection mode')
            $securityKey = Get-BoxBrainValue $detail @('Security key')
            $ssid = Get-BoxBrainValue $detail @('SSID name')
            if ($ssid) { $ssid = $ssid.Trim('"') } else { $ssid = $profileName }
            $profiles.Add([ordered]@{
                profile = $profileName
                ssid = $ssid
                interface = $name
                authentication = (Get-BoxBrainValue $detail @('Authentication'))
                encryption = (Get-BoxBrainValue $detail @('Cipher'))
                auto_connect = [bool]($mode -match 'automatically')
                priority = $priority
                credential_available = [bool]($securityKey -match 'Present')
            })
        }
    }
    return [ordered]@{
        schema_version = 1
        collected_at = [DateTime]::UtcNow.ToString('o')
        source = 'windows-supported-wlan-commands'
        credential_material_included = $false
        interfaces = @($interfaces)
        profiles = @($profiles)
    }
}

$inventory = Get-BoxBrainInventory
$reconnect = $null
if ($request.action -eq 'reconnect') {
    $profile = [string]$request.profile
    $interface = [string]$request.interface
    $known = @($inventory.profiles | Where-Object { $_.profile -eq $profile -and $_.interface -eq $interface })
    if ($known.Count -ne 1) { throw 'The requested WLAN profile/interface pair is not in inventory.' }
    $connectOutput = Invoke-BoxBrainNetsh @('wlan','connect',"name=$profile","interface=$interface")
    Start-Sleep -Seconds 2
    $inventory = Get-BoxBrainInventory
    $connected = @($inventory.interfaces | Where-Object { $_.name -eq $interface -and $_.profile -eq $profile -and $_.state -match 'connected' })
    $reconnect = [ordered]@{
        requested = $true
        profile = $profile
        interface = $interface
        connected = [bool]($connected.Count -eq 1)
        output_recorded = $false
    }
}
[ordered]@{ schema_version = 1; action = [string]$request.action; inventory = $inventory; reconnect = $reconnect } |
    ConvertTo-Json -Depth 8 -Compress
"""


def build_powershell(
    action: str,
    *,
    profile: str | None = None,
    interface: str | None = None,
) -> str:
    if action not in _ACTIONS:
        raise WindowsWlanError(f"Unsupported Windows WLAN action: {action}")
    request = {
        "action": action,
        "profile": profile,
        "interface": interface,
    }
    encoded = base64.b64encode(
        json.dumps(request, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    return _POWERSHELL.replace("__REQUEST__", encoded)


def parse_powershell_output(output: str) -> dict[str, Any]:
    for line in reversed(output.splitlines()):
        if not line.lstrip().startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict) or not isinstance(payload.get("inventory"), dict):
            continue
        inventory = payload["inventory"]
        if inventory.get("credential_material_included") is not False:
            raise WindowsWlanError("Windows WLAN inventory did not prove credential exclusion.")
        if not isinstance(inventory.get("interfaces"), list) or not isinstance(inventory.get("profiles"), list):
            raise WindowsWlanError("Windows WLAN inventory has an invalid schema.")
        return payload
    raise WindowsWlanError("Windows returned no usable WLAN inventory.")


def diagnose_inventory(inventory: dict[str, Any]) -> dict[str, Any]:
    findings: list[dict[str, str]] = []
    interfaces = [item for item in inventory.get("interfaces", []) if isinstance(item, dict)]
    profiles = [item for item in inventory.get("profiles", []) if isinstance(item, dict)]
    connected = [item for item in interfaces if "connected" in str(item.get("state", "")).lower()]
    if not interfaces:
        findings.append(
            {
                "severity": "high",
                "title": "No Windows wireless interface detected",
                "recommendation": "Check the WLAN adapter, driver, hardware switch, and airplane mode.",
            }
        )
    elif not connected:
        findings.append(
            {
                "severity": "medium",
                "title": "Windows WLAN is disconnected",
                "recommendation": "Use a known authorized saved profile or inspect signal and adapter state.",
            }
        )
    for item in connected:
        signal = item.get("signal_percent")
        if isinstance(signal, int) and signal < 35:
            findings.append(
                {
                    "severity": "low",
                    "title": "Windows WLAN signal is weak",
                    "recommendation": "Move closer to the access point or use Ethernet for repair operations.",
                }
            )
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "interface_count": len(interfaces),
        "connected_interface_count": len(connected),
        "profile_count": len(profiles),
        "auto_connect_profile_count": sum(item.get("auto_connect") is True for item in profiles),
        "recognized_ssids": sorted({str(item.get("ssid")) for item in profiles if item.get("ssid")}),
        "findings": findings,
    }


def load_saved_inventories(state_directory: str | Path) -> list[dict[str, Any]]:
    directory = Path(state_directory) / "network-inventory"
    records: list[dict[str, Any]] = []
    if not directory.is_dir():
        return records
    for path in sorted(directory.glob("*-windows-wlan.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            inventory = record["inventory"]
        except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError):
            continue
        if not isinstance(record, dict) or not isinstance(inventory, dict):
            continue
        if inventory.get("credential_material_included") is not False:
            continue
        records.append(record)
    return records
