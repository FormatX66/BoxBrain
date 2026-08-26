# Aurum Farmer v3.2

This directory preserves the reviewed v3.2 host package and its bounded ChatGPT
actuator. `install_aurum_farmer.py` performs a transactional, Last-Known-Good-
backed systemd promotion against the existing Aurum Slush database. It creates no
timer or polling loop; the Unix socket wakes the worker on real events.

The production Chat Tree MCP adapters expose the actuator from
`Projects/Aurum/ChatTreePlugin` and `Projects/Aurum/ChatTreeMCP`. The fixed GitHub
target is `FormatX66/Chat-to-Git-Pipeline`, where the v3.2 controller, executor,
and independent verifier own continuation to a terminal completion audit.

Host installation requires a reachable POSIX Aurum host with an existing valid
Slush database and elevated systemd authority. The installer stages LKG backups
and rolls back a failed promotion.
