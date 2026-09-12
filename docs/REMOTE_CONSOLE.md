# BoxBrain One Remote Console

BoxBrain One's browser console can be reached securely away from the local LAN by placing Tailscale Serve in front of the existing FastAPI controller.

## Recommended topology

```text
iPhone / laptop / tablet
        |
   Tailscale identity + tailnet policy
        |
     HTTPS :443
        |
   Tailscale Serve on BoxBrain Pi
        |
 http://127.0.0.1:8000
        |
 BoxBrain Controller + Web Console
```

The controller should remain private. Tailscale terminates HTTPS and proxies requests to the loopback controller. BoxBrain's own `X-BoxBrain-Token` authentication remains enabled as a second authorization layer.

## Pi setup

1. Install and authenticate Tailscale on the BoxBrain node.
2. Run the controller on loopback, normally port 8000.
3. Set a random `BOXBRAIN_API_TOKEN` of at least 32 characters.
4. Enable the remote console:

```bash
sudo bash deploy/remote-console/install-tailscale-serve.sh
```

If the controller uses another port:

```bash
sudo BOXBRAIN_CONTROLLER_PORT=8080 bash deploy/remote-console/install-tailscale-serve.sh
```

The installer prints the HTTPS tailnet URL returned by `tailscale serve status`.

## Client devices

Install Tailscale and sign into the approved tailnet on each phone, tablet, or computer that should reach BoxBrain. Open the HTTPS hostname shown by `tailscale serve status` in any modern browser. The same `/` and `/console` interface is used on every device.

## Access policy

Use a least-privilege Tailscale Grant/ACL so only approved identities or devices can reach the BoxBrain node. Do not grant the entire tailnet access unless that is intentional.

Keep the BoxBrain API token enabled even when Tailscale access policy is present. Store it in the console's session-scoped token field; do not place the token in the URL.

## Public-internet mode

Tailscale Funnel is intentionally **not enabled** by the BoxBrain installer. Funnel publishes a service to the broader internet, whereas Serve keeps it inside the tailnet. If a later BoxBrain deployment needs browser access without installing Tailscale on client devices, use a separately authenticated identity-aware proxy rather than simply switching the controller to a public bind address.

## Emergency shutdown

Remove remote publication immediately with:

```bash
sudo tailscale serve reset
```

This is separate from BoxBrain's application emergency stop. The BoxBrain emergency stop continues to block remote sessions and other consequential controller actions even while the console itself is reachable.

## Verification

On the Pi:

```bash
tailscale status
tailscale serve status
curl -fsS http://127.0.0.1:8000/api/v1/health
```

From an approved remote device, open the HTTPS tailnet URL, enter the BoxBrain API token, and verify that Health, Fleet, Remote Targets, Edge Agent, Agents, Tools, Projects, Activity, and Emergency Stop state load successfully.
