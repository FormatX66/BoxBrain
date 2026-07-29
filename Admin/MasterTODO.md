# Master TODO

## P0 — Repository integrity

- [x] Create the canonical BoxBrain indexes.
- [x] Register the existing BrainConnect repository.
- [x] Establish non-duplication and session-handoff rules.
- [x] Add structural and Markdown-link validation.
- [x] Confirm BoxBrain and BrainConnect remote repository URLs.
- [ ] Confirm project owners and priority ordering.
- [ ] Clarify the purpose and current assets for Arkmatx.

## P0 — BrainConnect

- [x] Implement the authenticated live event stream.
- [x] Specify observation-target identity and allowlisting.
- [x] Select an observation-only FreeRDP plugin boundary.
- [x] Define evidence retention and redaction policy.
- [x] Implement the durable target registry and audited enable/disable API.
- [x] Gate task creation on enabled target UUIDs.
- [x] Add the Flutter target registration and approval workflow.
- [x] Implement the certificate-probe process protocol and identity-mismatch
  handler.
- [x] Add the Flutter certificate-probe workflow.
- [x] Implement the native out-of-process FreeRDP certificate helper.
- [x] Build and synthetic-test the helper for amd64 and arm64.
- [x] Package and install the helper on the Kali Raspberry Pi 4.
- [x] Verify the installed checksum, ownership, provenance, and host-runtime
  synthetic boundary test.
- [x] Deploy and configure the FastAPI controller on the Raspberry Pi.
- [x] Verify authentication, USB-only binding, private state, helper integrity,
  emergency-stop persistence, and hardened service restart behavior.
- [x] Live-test exact-match, certificate-rotation, unreachable, timeout, and
  no-authentication behavior through a protocol-faithful Pi RDP/NLA fixture.
- [ ] Select a disposable full Windows VM or dedicated target for desktop and
  frame-transport testing; Windows Sandbox cannot host a second RDP listener.

Detailed implementation work belongs in the canonical
[BrainConnect roadmap](../../BrainConnect/docs/ROADMAP.md).

## P1 — Ecosystem discovery

- [ ] Locate or define WebsiteBuilder.
- [ ] Locate or define AgentFramework.
- [ ] Locate or define WebsiteCluster.
- [ ] Locate or define Automation.
- [ ] Create Security and Research repositories only when implementation work
  begins.

## P2 — Operations

- [x] Configure remote origins.
- [ ] Complete review and merge of the BoxBrain organization branch.
- [ ] Add CI for repository validation.
- [ ] Define release and archive procedures.
- [ ] Define Docker, Raspberry Pi, VM, and cloud deployment matrices.
