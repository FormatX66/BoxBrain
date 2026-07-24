# Security and Lab Boundaries

BoxBrain is intended for machines and accounts the operator owns or is
explicitly authorized to test. Initial executor development belongs in a
disposable VM or physically isolated lab target.

## Invariants

These remain active in every policy profile:

- Target allowlisting and visible target identity
- Immutable action and policy-decision logging
- A local emergency stop independent of the planner
- Secret redaction before model requests and logs
- Capability-scoped, out-of-process plugins
- No controller self-update during an active run
- No hidden persistence or privilege escalation

## Durable audit boundary

Task creation and its audit event are committed atomically. The event table has
no mutation API, and SQLite triggers reject direct updates or deletions. Runtime
data stays under `controller/data/` and is excluded from source control. The
authenticated event stream reads only forward from durable sequence numbers and
uses no mutable in-memory event queue.

## Read-only Windows Sandbox observer

The alpha observer captures only the visible Windows Sandbox window pixels. It
exposes target identity and PNG frames, but no keyboard, mouse, clipboard,
file, process, or shell operation. Frame responses are local-only and marked
`no-store`.

The supplied `sandbox/BoxBrain-Isolated.wsb` profile disables networking,
clipboard, audio/video input, printer redirection, and vGPU, and enables
Protected Client mode. Closing the Sandbox discards its contents.

In development, the dashboard may request that exact profile be opened. The
endpoint accepts no executable or path input, refuses non-`.wsb` profiles, and
records both successful and failed requests in the append-only event store. It
is disabled by default outside the development environment.

`research` and `open` may reduce per-action confirmations, but they do not
remove containment, logging, identity, or emergency-stop controls.

## Local API authentication

The controller optionally enforces a minimum-32-character token on all API
routes except health and documentation. The dashboard sends it only in the
`X-BoxBrain-Token` header, including authenticated in-memory frame requests.
CORS permits the header only from configured dashboard origins. Trusted Host
validation accepts only configured loopback names, reducing DNS-rebinding risk.
API responses disable caching, framing, referrers, MIME sniffing, and cross-site
resource use through explicit response headers.

The alpha web build receives its token at build time. This protects a loopback
development controller from accidental unauthenticated requests, but it is not
a substitute for user identity, OS-backed secret storage, TLS, or process
isolation. Never expose this controller or dashboard to another host.

## Emergency-stop boundary

The emergency-stop state is persisted in the controller database and remains
engaged across controller restarts. Engagement and reset requests are appended
to the immutable audit stream. While engaged, effectful controller requests
such as starting Windows Sandbox are rejected before the launcher is called;
read-only health, audit, target discovery, and frame observation remain
available. Reset requires the exact confirmation value `RESET`, and the
dashboard also requires an explicit typed confirmation.

All future executors and effectful plugins must acquire the same controller
action gate and re-check the persistent stop state before acting.

## Before adding an executor

- Use a VM snapshot with no sensitive files or credentials.
- Put the target on a dedicated network segment with explicit egress rules.
- Require mutual authentication between UI, controller, and plugins.
- Store provider credentials outside the repository and encrypt them at rest.
- Sign plugin packages and verify their hashes before activation.
- Define maximum task time, action count, cost, and data-transfer limits.
- Make restoration and evidence export part of the normal run lifecycle.

## Self-improvement boundary

BoxBrain may propose changes in a branch, run tests in a build sandbox, and
produce a review packet. It must not replace its running controller or merge its
own changes during an active session.

