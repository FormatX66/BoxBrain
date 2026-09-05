# Wi-Fi connection ownership and recovery

All native setup, HTML GUI, console and boot connection operations share a
nonblocking process lock. A busy request does not replace a saved profile or
launch another daemon. The graphical controls retain masked input until a
connection is verified, and do not submit overlapping scan/connect/disconnect
requests. Forget remains an explicit separate action.

Credentials are staged privately, outside Git. A new profile is committed only
after exact-SSID association, usable IPv4, a route on that interface, DNS and an
interface-bound GitHub TCP check pass. The previous saved profile is retained;
one bounded recovery attempt follows a failed connection trial. TCP reachability
is not itself verified HTTPS, Git sync or seed promotion.

NetworkManager is the sole Ethernet and Wi-Fi connection manager. Aurum never
starts, stops, signals, discovers, or cleans up a supplicant process and never
runs a second DHCP client. The packaged supplicant is available only as
NetworkManager's backend. The boot unit is a bounded readiness observer; the GUI
and local recovery console never wait for internet to render.

Persistence
proof uses a wireless-specific association and route snapshot, not the global
default interface. Legacy generic-online receipts cannot qualify Wi-Fi. After
the first verified wireless connection, a preserved-profile baseline is recorded
and another observed boot is required; no first connection is labeled reboot
proof. Profile loss/change and loss of previously verified wireless access still
fail closed. Earlier observations remain in the receipt as evidence.

Candidate profiles are written mode 0600 under NetworkManager's volatile
keyfile directory. The prior active profile remains available until exact Wi-Fi
and internet verification succeeds. Failure removes only the candidate and asks
NetworkManager to restore the prior UUID. Success copies the verified profile to
the persistent keyfile directory before deleting superseded Aurum-owned profiles.
Unrelated user or system profiles are never removed.

## Local verification

Run the AurumPC unit suite. `test_aurum_wifi_html_ownership.py` executes the shipped
JavaScript with deferred HTTP and DOM fixtures; it requires Node.js. Native GUI
input tests require Pygame. Skipped dependency gates are not passed gates.

These checks do not prove a physical WPA handshake, DHCP lease, Wi-Fi-only HTTPS,
saved-profile persistence after reboot, keyboard/trackpad, or seed promotion.
Release acceptance still needs the actual target and those observations. Preserve
Ethernet/recovery access, displaced runtime evidence and Last Known Good; never
use an unchanged reflash or blanket process kill as a connectivity workaround.
