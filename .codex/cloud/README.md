# BoxBrain Python cloud environment

Use this environment for controller, Farmer, repository validation and other
ordinary Python coding work. Builds and tests execute in the cloud, so their
dependency installation and worker memory do not run on Bruce's laptop.

## GitHub-hosted tests

The existing `BoxBrain CI` workflow uses GitHub-hosted Ubuntu and Windows runners.
Its backend job installs dependencies through `setup.sh` in this directory and
runs the controller and edge-agent suites. A pull request into `main` triggers
the checks. A bounded manual run is also available:

```sh
gh workflow run ci.yml --repo FormatX66/BoxBrain --ref YOUR_PUSHED_BRANCH -f mode=quick
```

Use the existing run for the same revision when it already supplies the needed
evidence. Do not dispatch another run solely to refresh a timestamp. The workflow
has job timeouts and cancellation for superseded runs. No deployment authority is
added by this setup.

## Codex cloud settings

- Repository: `FormatX66/BoxBrain`.
- Name: `BoxBrain Python cloud`.
- Image: `universal`; Python 3.12.
- Container caching: enabled.
- Agent internet access: disabled.
- Secrets: none required for these tests; do not add live hardware credentials.
- Setup and maintenance scripts: use the following inline command until this
  directory is merged into the default branch. Caching starts from that branch,
  so a setup script must not assume an unmerged file exists.

```sh
set -euo pipefail
python --version
python -m pip install --disable-pip-version-check -e ./Projects/AurumFarmer -e './controller[dev]'
python -m pip check
```

The maintenance script refreshes editable dependencies after the selected branch
is checked out. After merge, both fields can use `bash .codex/cloud/setup.sh`.
The setup itself installs packages only; it does not start the resident Farmer,
contact hardware, call a paid model API or deploy a release.

Useful bounded commands after setup:

```sh
python Admin/validate_repository.py
python -m unittest Admin.tests.test_validate_repository -q
(cd controller && python -m pytest -q)
python -m unittest discover -s Projects/AurumFarmer/tests -q
```

Select the intended branch or exact revision in Codex before starting work.
Cloud tasks do not inherit uncommitted Windows files, local hub state, running
services, loopback endpoints or hardware access. Carry only the concise task
instructions and evidence needed for the work. Preserve the repository's Future
Branch and Last Known Good rules.

## VM and rollback boundary

The live Hopper QEMU VM, USB and boot qualification remain with their local owners.
GitHub-hosted runners do not officially support nested virtualization; a Codex
container is not a drop-in host for the persistent VM. Any separate VM proposal
needs verified virtualization support, storage/checkpoint handling, connectivity,
an explicit cost limit and independent recovery validation before migration.

This change leaves running services and default-branch settings untouched until
review and merge. Close the draft PR to discard the repository change. The cloud
environment can be edited or removed independently; retain its settings and test
receipt before a later change. Never stop the resident explorer as cleanup.

References: [Codex cloud environments](https://learn.chatgpt.com/docs/environments/cloud-environment)
and [GitHub-hosted runners](https://docs.github.com/en/actions/concepts/runners/github-hosted-runners).
