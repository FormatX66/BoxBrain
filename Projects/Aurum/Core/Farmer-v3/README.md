# Aurum Farmer v3.3

This directory extends the v3.2 host package with Decision Engine v1 and its bounded ChatGPT
actuator. `install_aurum_farmer.py` performs a transactional, Last-Known-Good-
backed systemd promotion against the existing Aurum Slush database. It creates no
timer or polling loop; the Unix socket wakes the worker on real events.

Every bounded tool dispatch records a decision DAG and prediction/outcome pair,
while pending ingress is explored concurrently. The shared engine source is
`../../../AurumFarmer/aurum_farmer/decision_engine.py`. The transactional installer
stages it beside the worker and restores it with the other files on failed
promotion. Standalone archives must include that module as `decision_engine.py`.
The existing GitHub actuator/controller protocol and seed sync behavior remain
compatible. Tool-contract verification does not imply physical acceptance.

The production Chat Tree MCP adapters expose the actuator from
`Projects/Aurum/ChatTreePlugin` and `Projects/Aurum/ChatTreeMCP`. The fixed GitHub
target is `FormatX66/Chat-to-Git-Pipeline`, where the v3.2 controller, executor,
and independent verifier own continuation to a terminal completion audit.

Host installation requires a reachable POSIX Aurum host with an existing valid
Slush database and elevated systemd authority. The installer stages LKG backups
and rolls back a failed promotion.
