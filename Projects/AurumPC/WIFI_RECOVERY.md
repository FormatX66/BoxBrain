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

The supplicant runs in an independent transient system service, with bounded
startup/shutdown, PID tracking and no automatic restart loop. It does not share
the GUI or console service lifetime. Boot reconnect remains a bounded request;
the GUI and local recovery console never wait for internet to render.

Replacement stops only an exact Aurum-owned process using a kernel PID handle,
waits for process exit and service PID-file cleanup, and refuses incomplete or
unknown ownership. A missing PID record requires a unique match across executable,
root ownership, exact interface/configuration arguments and the actual control
socket descriptor. An occupied foreign socket is never removed or killed.

## Local verification

Run the AurumPC unit suite. `test_aurum_wifi_html_ownership.py` executes the shipped
JavaScript with deferred HTTP and DOM fixtures; it requires Node.js. Native GUI
input tests require Pygame. Skipped dependency gates are not passed gates.

An additional Linux canary uses only temporary **user** services, synthetic
children and temporary files, not a network interface:

```sh
python3 Projects/AurumPC/tests/wifi_service_lifetime_canary.py
```

It must run unprivileged with an active user systemd manager. It compares
caller-coupled and independent lifetimes, then exercises the candidate's actual
service-launch arguments with a synthetic forking daemon. It verifies the child
survives caller shutdown and PID-file cleanup completes after owned service stop.
It refuses root and cleans only its uniquely named test services.

These checks do not prove a physical WPA handshake, DHCP lease, Wi-Fi-only HTTPS,
saved-profile persistence after reboot, keyboard/trackpad, or seed promotion.
Release acceptance still needs the actual target and those observations. Preserve
Ethernet/recovery access, displaced runtime evidence and Last Known Good; never
use an unchanged reflash or blanket process kill to work around an occupied socket.
