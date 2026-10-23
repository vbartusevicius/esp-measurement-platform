#!/bin/bash
# Reports unused includes in lib/ and src/ (clang-tidy include cleaner on the
# xiao_c6 build). Run in the firmware container:
#   docker run --rm -v "$PWD":/project -v esp-pio:/root/.platformio esp-firmware "bash tools/check_includes.sh"
# Umbrella headers (<Arduino.h>, <ArduinoJson.h>) can show up as "not used
# directly"; they are the libraries' public headers, keep them.
set -e
apt-get update -qq >/dev/null && apt-get install -y -qq clang-tidy >/dev/null 2>&1
pio run -e xiao_c6 -t compiledb >/dev/null 2>&1
mkdir -p /tmp/tidydb
export PATH=$PATH:/root/.platformio/packages/toolchain-riscv32-esp/bin
GXX=riscv32-esp-elf-g++
SYS=$($GXX -xc++ -E -v - </dev/null 2>&1 | sed -n '/#include <...> search starts here:/,/End of search list./p' | grep '^ ' | sed 's/^ *//' | while read -r d; do readlink -f "$d"; done)
python3 - "$SYS" <<'EOF'
import json, shlex, sys
drop = {'-fno-tree-switch-conversion', '-fstrict-volatile-bitfields', '-mtext-section-literals', '-mlongcalls',
        '-fno-jump-tables', '-mdisable-hardware-atomics', '-fno-shrink-wrap', '-freorder-blocks', '-fipa-pta', '-free'}
sysdirs = [d for d in sys.argv[1].split('\n') if d]
db = json.load(open('compile_commands.json'))
out = []
for e in db:
    f = e['file']
    if not (f.startswith('lib/') or f.startswith('src/')) or 'WebAssets' in f:
        continue
    args = shlex.split(e['command'])
    args = [a for a in args if a not in drop and not a.startswith('-march=') and not a.startswith('-mabi=')]
    args = ['clang++', '--target=riscv32-unknown-elf', '-march=rv32imac', '-mabi=ilp32'] + args[1:]
    for d in sysdirs:
        args += ['-isystem', d]
    out.append({'directory': e['directory'], 'file': f, 'arguments': args})
json.dump(out, open('/tmp/tidydb/compile_commands.json', 'w'))
print(f'{len(out)} project translation units')
EOF
FILES=$(python3 -c "import json;print(' '.join(sorted({e['file'] for e in json.load(open('/tmp/tidydb/compile_commands.json'))})))")
clang-tidy -p /tmp/tidydb --quiet \
  --checks='-*,misc-include-cleaner' \
  --config="{CheckOptions: {misc-include-cleaner.MissingIncludes: false}}" \
  --header-filter='/project/(lib|src)/.*' \
  $FILES 2>&1 > /tmp/tidy.log || true
echo "compile errors in project files: $(grep -c 'error:' /tmp/tidy.log)"
grep -E "error:" /tmp/tidy.log | sort -u | head -5
grep -E "is not used directly" /tmp/tidy.log | grep -v WebAssets.h | sort -u
