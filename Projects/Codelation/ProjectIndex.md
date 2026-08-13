# Codelation Project Index

- Status: experimental seed plus isolated machine-native storage capability
- Priority: P1
- Platform: carrier-independent logical model; Python reference on current hosts
- Design: [README](README.md)
- Bootstrap seed: [codelation_seed.py](seed/codelation_seed.py)
- Seed tests: [test_seed.py](tests/test_seed.py)
- Aurum Field v0: [format](field/FIELD_FORMAT.md), [reference capability carrier](field/aurum_field.py), [tests](tests/test_aurum_field.py)

The original milestone remains a passive, binary state-transition learner. It has no
actuation authority and does not treat observations as executable commands.

Aurum Field v0 is a separate storage experiment. It models immutable,
self-addressed grains and relationships rather than disks, clusters, paths,
tables, or application-owned stores. Existing JSON/JSONL state remains
authoritative while the field is tested as an isolated capability.
