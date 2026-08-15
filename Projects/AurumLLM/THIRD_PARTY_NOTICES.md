# Third-Party Notices

Aurum LLM Core v0.01 bootstraps from third-party open-source components. These components are seeds and runtime dependencies; Aurum's stable interface and orchestration remain in this repository.

## llama.cpp

- Project: `ggml-org/llama.cpp`
- Reference release: `b10173`
- License: MIT
- The build copies the upstream LICENSE into the produced bundle.

## Qwen3.5-0.8B seed model

- Upstream model: `Qwen/Qwen3.5-0.8B`
- Reference GGUF conversion: `ggml-org/Qwen3.5-0.8B-GGUF`
- Reference file: `Qwen3.5-0.8B-Q4_0.gguf`
- Reference revision: `8fea620`
- License: Apache-2.0
- The build copies the Apache-2.0 license into the produced bundle.

Model provenance, runtime commit identity, and content hashes are recorded in `runtime-manifest.json` in every built artifact.
