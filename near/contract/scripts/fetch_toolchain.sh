#!/bin/bash
# Populate the near-sdk-js build toolchain (binaryen, QuickJS, wasi-sdk)
# into node_modules/near-sdk-js/lib/cli/deps/, the layout the SDK's own
# postinstall would create.
#
# Why this exists: the SDK postinstall downloads these from GitHub with
# a fetcher that ignores the proxy env, so through this VM's egress it
# fails AFTER wiping the deps folder (review round 1, M-2). curl honors
# the proxy. This script is idempotent: re-running it repairs a wiped
# or partial deps folder. Run order:
#   npm install --ignore-scripts --no-audit --no-fund
#   npm run setup
set -eu
cd "$(dirname "$0")/.."
DEPS=node_modules/near-sdk-js/lib/cli/deps
if [ ! -d node_modules/near-sdk-js ]; then
  echo "near-sdk-js is not installed; run npm install --ignore-scripts first" >&2
  exit 1
fi
mkdir -p "$DEPS"
cd "$DEPS"

if [ ! -f binaryen/lib/libbinaryen.so ]; then
  curl -sSL -o b.tgz https://github.com/ailisp/binaryen/releases/download/v0.1.16/binaryen-Linux-X64.tar.gz
  mkdir -p binaryen && tar xzf b.tgz --directory binaryen || true
  rm -f b.tgz
fi
if [ ! -x qjsc ]; then
  curl -sSL -o qjsc https://github.com/near/quickjs/releases/download/v0.1.3/qjsc-Linux-X64
  chmod 755 qjsc
fi
if [ ! -d quickjs ]; then
  curl -sSL -o q.tgz https://github.com/near/quickjs/archive/refs/tags/v0.1.3.tar.gz
  tar xzf q.tgz && mv quickjs-0.1.3 quickjs && rm -f q.tgz
fi
if [ ! -d wasi-sdk ]; then
  curl -sSL -o w.tgz https://github.com/WebAssembly/wasi-sdk/releases/download/wasi-sdk-11/wasi-sdk-11.0-linux.tar.gz
  tar xzf w.tgz && mv wasi-sdk-11.0 wasi-sdk && rm -f w.tgz
fi

# Verify the four pieces the builder needs.
test -f binaryen/lib/libbinaryen.so
test -x binaryen/wasi-stub/wasi-stub || test -f binaryen/wasi-stub/run.sh
test -x qjsc
test -d quickjs
test -d wasi-sdk
echo "toolchain deps OK in $DEPS"
