# Give Aurum a Build Lane

Aurum can use independent GitHub-hosted build and verification lanes contributed by volunteers through public forks of BoxBrain.

## Join in three steps

1. Create a free GitHub account if you do not already have one.
2. Fork `FormatX66/BoxBrain` into your account and enable GitHub Actions on that fork.
3. Open the **Join the Aurum Build** issue form in the upstream BoxBrain repository and submit your fork plus your preferred contribution type.

Once Actions are enabled, the fork's **Aurum Contributor Lane** checks the authoritative Aurum trunk on a bounded schedule. Each fork receives a deterministic independent test shard based on its GitHub owner identity. If that fork already verified the current Aurum commit, it skips the work instead of repeating it.

## What you are contributing

You are opting in to let your public fork run bounded GitHub-hosted Actions jobs for independent Aurum build, test, portability, or verification work. You are not giving Aurum access to your personal computer, personal files, credentials, private repositories, or other GitHub projects.

Aurum contributor lanes check out the authoritative `aurum/trunk-v0.01` source read-only and return evidence only. They do not receive write authority over the trusted Aurum generation and cannot promote code to Hopper.

## Stop at any time

Disable GitHub Actions on your fork or delete the fork. No additional shutdown procedure is required.

## Why independent lanes matter

Aurum prefers useful parallel work over duplicate work. Contributor capacity is most valuable when it verifies a different test shard, architecture, implementation candidate, or failure mode. The trusted Aurum promotion path still requires verified convergence before changes reach physical nodes.
