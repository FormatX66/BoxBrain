#!/bin/sh
set -eu

VERSION="${AURUM_LLM_VERSION:-0.01}"
ARCH="${AURUM_ARCH:-$(uname -m)}"
case "$ARCH" in
  x86_64|amd64) ARCH="x86_64" ;;
  *)
    echo "Unsupported Aurum LLM reference architecture: $ARCH" >&2
    exit 2
    ;;
esac

RUNTIME_TAG="${AURUM_LLAMA_CPP_TAG:-b10173}"
MODEL_REPO="${AURUM_MODEL_REPO:-ggml-org/Qwen3.5-0.8B-GGUF}"
MODEL_REVISION="${AURUM_MODEL_REVISION:-8fea620}"
MODEL_FILE="${AURUM_MODEL_FILE:-Qwen3.5-0.8B-Q4_0.gguf}"
MODEL_URL="https://huggingface.co/${MODEL_REPO}/resolve/${MODEL_REVISION}/${MODEL_FILE}?download=true"
JOBS="${AURUM_BUILD_JOBS:-$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 2)}"

ROOT="$(pwd)"
BUILD_ROOT="$ROOT/Projects/AurumLLM/.build"
RUNTIME_SRC="$BUILD_ROOT/llama.cpp"
RUNTIME_BUILD="$BUILD_ROOT/llama-build"
OUT="$ROOT/dist/Aurum-LLM-v${VERSION}-${ARCH}"

rm -rf "$BUILD_ROOT" "$OUT"
mkdir -p "$BUILD_ROOT" "$OUT/bin" "$OUT/models" "$OUT/config" "$OUT/licenses"

printf '%s\n' "AURUM_LLM_BUILD version=$VERSION arch=$ARCH runtime=$RUNTIME_TAG model=$MODEL_REPO@$MODEL_REVISION/$MODEL_FILE"

git clone --depth 1 --branch "$RUNTIME_TAG" https://github.com/ggml-org/llama.cpp.git "$RUNTIME_SRC"

cmake -S "$RUNTIME_SRC" -B "$RUNTIME_BUILD" \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_SHARED_LIBS=OFF \
  -DGGML_NATIVE=OFF \
  -DGGML_OPENMP=OFF \
  -DLLAMA_CURL=OFF
cmake --build "$RUNTIME_BUILD" -j "$JOBS" --target llama-cli llama-server

cp "$RUNTIME_BUILD/bin/llama-cli" "$OUT/bin/llama-cli"
cp "$RUNTIME_BUILD/bin/llama-server" "$OUT/bin/llama-server"
chmod 0755 "$OUT/bin/llama-cli" "$OUT/bin/llama-server"

curl --location --fail --retry 4 --retry-all-errors --retry-delay 2 \
  "$MODEL_URL" \
  --output "$OUT/models/seed.gguf"
test -s "$OUT/models/seed.gguf"

cp Projects/AurumLLM/seed-model.json "$OUT/config/seed-model.json"
cp Projects/AurumLLM/system.txt "$OUT/config/system.txt"
cp Projects/AurumLLM/THIRD_PARTY_NOTICES.md "$OUT/THIRD_PARTY_NOTICES.md"
cp "$RUNTIME_SRC/LICENSE" "$OUT/licenses/llama.cpp-MIT.txt"
if [ -f /usr/share/common-licenses/Apache-2.0 ]; then
  cp /usr/share/common-licenses/Apache-2.0 "$OUT/licenses/Qwen-Apache-2.0.txt"
else
  echo "Debian Apache-2.0 common license file was not available." >&2
  exit 3
fi

MODEL_SHA="$(sha256sum "$OUT/models/seed.gguf" | awk '{print $1}')"
CLI_SHA="$(sha256sum "$OUT/bin/llama-cli" | awk '{print $1}')"
SERVER_SHA="$(sha256sum "$OUT/bin/llama-server" | awk '{print $1}')"
RUNTIME_COMMIT="$(git -C "$RUNTIME_SRC" rev-parse HEAD)"

cat > "$OUT/runtime-manifest.json" <<EOF
{
  "schema": "aurum-llm-runtime-manifest-v0",
  "version": "$VERSION",
  "architecture": "$ARCH",
  "interface": "aurum-local-llm",
  "model_alias": "aurum-seed",
  "runtime": {
    "repository": "ggml-org/llama.cpp",
    "release": "$RUNTIME_TAG",
    "commit": "$RUNTIME_COMMIT",
    "llama_cli_sha256": "$CLI_SHA",
    "llama_server_sha256": "$SERVER_SHA"
  },
  "seed_model": {
    "repository": "$MODEL_REPO",
    "revision": "$MODEL_REVISION",
    "source_file": "$MODEL_FILE",
    "bundle_file": "models/seed.gguf",
    "sha256": "$MODEL_SHA"
  },
  "defaults": {
    "listen": "127.0.0.1:8080",
    "context_tokens": 2048,
    "parallel_slots": 1,
    "remote_inference_required": false
  }
}
EOF

(
  cd "$OUT"
  sha256sum \
    bin/llama-cli \
    bin/llama-server \
    models/seed.gguf \
    config/seed-model.json \
    config/system.txt \
    licenses/llama.cpp-MIT.txt \
    licenses/Qwen-Apache-2.0.txt \
    THIRD_PARTY_NOTICES.md \
    runtime-manifest.json \
    > SHA256SUMS
)

printf '%s\n' "AURUM_LLM_BUNDLE_READY path=$OUT"
ls -lh "$OUT/bin/llama-cli" "$OUT/bin/llama-server" "$OUT/models/seed.gguf"
