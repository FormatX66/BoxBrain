# BoxBrain Windows WLAN Integration

BoxBrain collects structured wireless-network metadata from an already
authorized Windows target through the existing SSH/JEA management link. The
same path works when the Pi reaches the target over its dedicated USB network
or another authorized private network; BoxBrain does not create a second remote
management subsystem for WLAN operations.

## Credential boundary

The inventory collector uses supported Windows commands:

- `netsh wlan show interfaces`
- `netsh wlan show profiles`
- `netsh wlan show profile` without `key=clear`
- `Get-NetAdapter -Physical`
- `Get-NetIPConfiguration`
- `Get-DnsClientServerAddress`

It never reads protected WLAN profile files and never requests, returns, stores,
or logs a password, passphrase, PSK, or `Key Content`. A saved profile contains
only `credential_available: true|false`, derived from the ordinary `Security
key: Present` profile summary. Every structured inventory explicitly records
`credential_material_included: false`; responses that cannot prove that
boundary are rejected.

If the restricted Windows account cannot open the `Get-NetAdapter` CIM
session, the collector falls back to the physical WLAN interfaces reported by
`netsh` and attempts IP/DNS metadata independently. A single unavailable
supported source therefore does not expose credentials or discard the rest of
the read-only inventory.

The separate, administrator-approved current-profile provisioning workflow is
not part of inventory. It retains its own consent, USB transport, standard-input,
and no-logging boundaries.

## Inventory

Interface records include:

- interface name, GUID, and description;
- connection state, current SSID/profile, and signal percentage;
- IPv4 addresses, gateways, and DNS servers;
- current authentication and encryption when Windows reports them.

Saved profile records include profile/SSID, interface, authentication,
encryption, auto-connect state, priority/order, and `credential_available`.
Inventory snapshots are stored under `/var/lib/boxbrain/network-inventory` for
network recognition and recovery planning. The BoxBrain dashboard Networks
section renders this metadata without credential values.

## CLI

All commands require an enrolled, currently connected, private/link-local
Windows target:

```sh
boxbrainctl windows-wlan 10.12.194.2 interfaces
boxbrainctl windows-wlan 10.12.194.2 profiles
boxbrainctl windows-wlan 10.12.194.2 status
boxbrainctl windows-wlan 10.12.194.2 diagnose
```

`diagnose` reports adapter/profile counts, recognized SSIDs, auto-connect
coverage, disconnected state, and weak-signal findings. It is also included in
the normal target health assessment.

Reconnect is the only modifying WLAN operation. It accepts only an exact
profile/interface pair already present in the collected inventory and requires
both the CLI authorization switch and exact confirmation:

```sh
boxbrainctl windows-wlan 10.12.194.2 reconnect \
  --profile 'Authorized-Lab' \
  --interface 'Wi-Fi' \
  --authorized \
  --confirmation 'RECONNECT WINDOWS WLAN'
```

Parameters are JSON/Base64 encoded into the fixed PowerShell collector instead
of interpolated into shell text. Windows re-enumerates inventory after the
reconnect attempt, and BoxBrain records the resulting connection state without
recording the command output or any credential material.

## Recovery use

During USB or network recovery, BoxBrain can compare the current SSID with the
saved, ordered profiles in the latest metadata snapshot. It may request a
reconnect only to an existing authorized profile. Adding or extracting a
credential remains a separate operator-approved provisioning action.
