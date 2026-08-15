# Aurum LLM Core v0.01

Aurum LLM Core is the local language-model interface lane for Aurum. The open-source model is a bootstrap seed, not the long-term identity of the system.

## Build architecture

This lane intentionally follows the same staged architecture as the Aurum PC and self-kernel lanes:

1. validate bounded source files and unit contracts;
2. build the runtime inside a Debian Bookworm container;
3. assemble a self-contained versioned bundle;
4. checksum the bundle contents;
5. start the built runtime outside the build container;
6. perform a real local inference/API smoke test;
7. record provenance and publish the verified artifact.

A failed LLM build is local to this lane and does not block the OS or adaptive-kernel lanes.

## Seed stack

The initial reference stack is deliberately small enough for hosted CPU validation:

- runtime: `llama.cpp` release `b10173`;
- seed model: `ggml-org/Qwen3.5-0.8B-GGUF`;
- seed file: `Qwen3.5-0.8B-Q4_0.gguf`;
- model license: Apache-2.0;
- runtime license: MIT.

The build keeps the model behind the Aurum-owned interface in `aurum_llm.py`. Higher Aurum layers should depend on that interface rather than on Qwen, GGUF, or llama.cpp directly. That makes the seed replaceable without rewriting the rest of Aurum.

## Local interface contract

The reference runtime binds to loopback by default and exposes an OpenAI-compatible local HTTP surface. `aurum_llm.py` provides Aurum's stable client contract on top of that surface:

- health/readiness;
- chat messages;
- optional tool schemas;
- content, reasoning-content, and tool-call capture;
- no required third-party Python packages.

The reference model alias is `aurum-seed`.

## Direction after seed boot

The intended progression is:

- bootstrap from a permissively licensed open model;
- attach Aurum memory/context retrieval before every inference;
- make tool calls and machine-state events first-class inputs/outputs;
- select model size and backend from observed hardware capacity;
- add LoRA/adapters and bounded fine-tuning from verified Aurum traces;
- maintain model lineage, evaluation evidence, and rollback checkpoints;
- replace the generic seed checkpoint with Aurum-derived checkpoints when evidence shows they are better;
- preserve the same Aurum LLM interface while the underlying model changes.

The LLM is therefore a core interface point, but not an authority bypass. Deterministic operations, verification, physical evidence, and safety gates remain outside the model and can reject model proposals.

## Build

Run from the repository root inside a Debian Bookworm environment with the required build tools installed:

```sh
sh Projects/AurumLLM/build-llm.sh
```

The output bundle is written to `dist/Aurum-LLM-v0.01-x86_64/`.
