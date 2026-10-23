#!/bin/bash
# Generates compile_commands.json and .clangd for clangd IDE support.
# Run once after cloning, or after changing platformio.ini dependencies.
#
# Usage: ./setup-ide.sh

set -e

PLATFORMIO_CORE_DIR="${PLATFORMIO_CORE_DIR:-$HOME/.platformio}"
TOOLCHAIN_DIR="$PLATFORMIO_CORE_DIR/packages/toolchain-riscv32-esp"

echo "Generating compile_commands.json..."
pio run -e xiao_c6 -t compiledb

if [ ! -d "$TOOLCHAIN_DIR" ]; then
    echo "Error: toolchain not found at $TOOLCHAIN_DIR"
    exit 1
fi

# The cross compiler knows its own C/C++ system include directories.
SYSTEM_INCLUDES=$("$TOOLCHAIN_DIR/bin/riscv32-esp-elf-g++" -xc++ -E -v - </dev/null 2>&1 \
    | sed -n '/#include <...> search starts here:/,/End of search list./p' | grep '^ ' | sed 's/^ */    - -isystem/')

echo "Generating .clangd with the riscv32-esp toolchain paths..."
cat > .clangd <<EOF
# Firmware sources: riscv32-esp cross-compiler flags from compile_commands.json
If:
  PathExclude: test/.*
CompileFlags:
  CompilationDatabase: .
  Add:
    - --target=riscv32-unknown-elf
    - -Wno-unused-command-line-argument
    - -Wno-unknown-warning-option
${SYSTEM_INCLUDES}
  Remove:
    - -march=*
    - -mabi=*
    - -fno-tree-switch-conversion
    - -fstrict-volatile-bitfields
    - -fno-shrink-wrap
EOF
# Note: native tests use test/compile_flags.txt instead of this file.

echo "Done. Restart clangd in your IDE to apply."
