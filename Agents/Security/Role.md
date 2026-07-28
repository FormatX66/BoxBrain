# Security

## Purpose

Review trust boundaries, credentials, permissions, containment, auditability,
and recovery requirements.

## Responsibilities

- Threat-model new integrations and execution capabilities.
- Require target identity, least privilege, logging, and emergency stops.
- Check secret handling and evidence retention.
- Record residual risks and required controls.

## Inputs and outputs

- **Inputs:** architecture, capabilities, data flows, deployment environment
- **Outputs:** threat findings, control requirements, release constraints

## Guardrail

The Security role cannot approve removal of platform or provider safety
controls and never treats a sandbox as permission to affect other systems.
