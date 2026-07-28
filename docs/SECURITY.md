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

The alpha observer captures only the visible Windows Sandbox window pixels. Its
status and PNG capture operations run in the enabled
`boxbrain.windows-sandbox-observer` child process. The controller verifies the
strict manifest, protocol/plugin/request/target identities, declared read-only
capabilities, response size, PNG signature, and SHA-256 frame digest. It exposes
no keyboard, mouse, clipboard, file, process, shell, or launch operation. Frame
responses are local-only and marked `no-store`. Response headers also expose the
frame digest, configured size limits, active redaction count, and retention mode.

The strict policy in `policies/observation.json` permits only zero evidence
retention. Configured normalized black masks are applied to the resized image in
the child before the PNG crosses the process boundary. The default policy has no
mask regions, so operators must deliberately configure regions that cover their
lab layout. Frames are never written to disk, and overlapping captures fail with
HTTP 429 instead of spawning another child process.

The child receives a stripped environment without the controller API token and
has a fixed deadline, but it still runs under the same Windows user. This is an
out-of-process fault and protocol boundary, not a lower-privilege OS sandbox.
Do not treat it as protection from malicious plugin code; restricted identities
and signed packages remain required before third-party plugins are supported.

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
a substitute for user identity, OS-backed secret storage, or process isolation.
Never expose this controller or dashboard to another host.

## Local HTTPS boundary

The Windows development helpers create a BoxBrain-only root CA and localhost
server certificate in the current user's certificate stores. They do not add
machine-wide trust or require administrator access. The server certificate is
valid only for `localhost`, `127.0.0.1`, and `::1`; both services remain bound
to IPv4 loopback.

The exported server private key stays under ignored `controller/data/tls/` and
its ACL is narrowed to the current Windows user. Exact certificate thumbprints
are recorded in ignored metadata. `remove-local-tls.ps1` uses only those
thumbprints and that verified directory for reversible cleanup. This CA is for
local development only and must never sign certificates for another service.

## Authorized remote targets

The connected-host manager stores only target identity and connection metadata.
It resolves a target before each probe or session and rejects any result outside
private, loopback, or link-local address space. Public, multicast, and
unspecified addresses are denied. Probes are limited to the registered TCP
endpoint.

Session routes choose only a fixed SSH, WinRM, RDP, or Telnet client argument
list and accept no shell commands. Every launch requires `OPEN`, is audited, and
is blocked by the persistent emergency stop. Telnet is available only for an
explicitly acknowledged lab profile and requires the additional exact phrase
`I UNDERSTAND TELNET IS PLAINTEXT`. BoxBrain has no password field or credential
store; use an SSH agent, the dedicated Pi key, the current Windows identity, or
an operating-system credential prompt.

An opened client remains a human-operated OS process. It is not contained by
BoxBrain and inherits the signed-in user's privileges, so operators must verify
the visible host identity and close the session when finished. Queued or model
processing tasks have no handle to these clients.

## Approval-gated Kali Pi diagnostics

The diagnostic model has no tools. Its Pydantic output can select only four
read-only action identifiers; summaries and prompt content never become process
arguments. The operator must inspect each proposal and type `RUN`. Proposals
expire after ten minutes, transition atomically out of `pending`, and cannot be
executed twice.

The executor is limited to the built-in Kali Pi identity. It reuses private-scope
resolution, strict SSH host-key checking, batch authentication, the dedicated Pi
key when present, a command deadline, and a 32 KiB output cap. The mapping from
action identifier to remote command is a source-controlled constant. No API
field accepts executable text, arguments, paths, service names, or environment
variables.

Raw diagnostic output is treated as untrusted display data. It is returned only
to the authenticated operator, is not sent back to the model, and is not copied
into the append-only audit event. Audit records retain only action, status, exit
code, duration, truncation state, model, token use, and proposal identity.

## Emergency-stop boundary

The emergency-stop state is persisted in the controller database and remains
engaged across controller restarts. Engagement and reset requests are appended
to the immutable audit stream. While engaged, effectful controller requests
such as starting Windows Sandbox are rejected before the launcher is called;
read-only health, audit, target discovery, and frame observation remain
available. Reset requires the exact confirmation value `RESET`, and the
dashboard also requires an explicit typed confirmation.

The diagnostic executor acquires this controller action gate and rechecks the
persistent stop before SSH starts. All future executors and effectful plugins
must use the same boundary.

## Before adding a broader executor

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
