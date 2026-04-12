#!/bin/bash
# Generates compile_commands.json and .clangd for clangd IDE support.
# Run once after cloning, or after changing platformio.ini dependencies.
#
# Usage: ./setup-ide.sh

set -e

PLATFORMIO_CORE_DIR="${PLATFORMIO_CORE_DIR:-$HOME/.platformio}"
TOOLCHAIN_DIR="$PLATFORMIO_CORE_DIR/packages/toolchain-xtensa"

if [ ! -d "$TOOLCHAIN_DIR" ]; then
    echo "Error: Toolchain not found at $TOOLCHAIN_DIR"
    echo "Run 'pio run' first to install dependencies."
    exit 1
fi

# Detect GCC version inside the toolchain
GCC_VERSION=$(ls "$TOOLCHAIN_DIR/lib/gcc/xtensa-lx106-elf/" | head -1)

echo "Generating compile_commands.json..."
pio run -e nodemcu -t compiledb

echo "Generating .clangd with toolchain paths (GCC $GCC_VERSION)..."
cat > .clangd <<EOF
CompileFlags:
  CompilationDatabase: .
  Add:
    - -Wno-unused-command-line-argument
    - -Wno-attributes
    - -isystem${TOOLCHAIN_DIR}/xtensa-lx106-elf/include/c++/${GCC_VERSION}
    - -isystem${TOOLCHAIN_DIR}/xtensa-lx106-elf/include/c++/${GCC_VERSION}/xtensa-lx106-elf
    - -isystem${TOOLCHAIN_DIR}/xtensa-lx106-elf/include/c++/${GCC_VERSION}/backward
    - -isystem${TOOLCHAIN_DIR}/lib/gcc/xtensa-lx106-elf/${GCC_VERSION}/include
    - -isystem${TOOLCHAIN_DIR}/lib/gcc/xtensa-lx106-elf/${GCC_VERSION}/include-fixed
    - -isystem${TOOLCHAIN_DIR}/xtensa-lx106-elf/include
    - --target=xtensa
  Remove:
    - -mlongcalls
    - -mtext-section-literals
    - -free
    - -fipa-pta
    - -falign-functions=4
EOF

echo "Done. Restart clangd in your IDE to apply."
