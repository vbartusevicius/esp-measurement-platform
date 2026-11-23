# EDA toolchain: KiCad 10.0.6 (kicad-cli + pcbnew Python bindings) via the
# official kicad/kicad:10.0 image (Debian trixie, amd64 emulation on arm64),
# SKiDL for circuit authoring, kinet2pcb for netlist-to-board conversion and
# fastroute (Rust port of Freerouting, DSN in / SES out) for `layout.py route`.
FROM --platform=linux/amd64 kicad/kicad:10.0

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       python3-pip python3-venv curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# The venv shares the system site-packages so that `python3` sees both the
# distro's pcbnew bindings and the pip-installed SKiDL/kinet2pcb/pytest.
RUN python3 -m venv --system-site-packages /opt/eda \
    && /opt/eda/bin/pip install --no-cache-dir \
       skidl==2.3.0 \
       kinet2pcb==1.1.4 \
       pyyaml==6.0.3 \
       pytest==8.4.2 \
       pillow==11.3.0 \
       shapely==2.1.1 \
       ortools==9.15.6755

# SKiDL discovers KiCad's stock libraries through these variables.
ENV KICAD10_SYMBOL_DIR=/usr/share/kicad/symbols \
    KICAD_SYMBOL_DIR=/usr/share/kicad/symbols \
    KICAD10_FOOTPRINT_DIR=/usr/share/kicad/footprints \
    KICAD9_SYMBOL_DIR=/usr/share/kicad/symbols \
    KICAD9_FOOTPRINT_DIR=/usr/share/kicad/footprints \
    PATH=/opt/eda/bin:$PATH
RUN mkdir -p /root/.config/kicad/10.0 \
    && cp /usr/share/kicad/template/fp-lib-table /root/.config/kicad/10.0/fp-lib-table \
    && cp /usr/share/kicad/template/fp-lib-table /root/.config/kicad/fp-lib-table \
    && cp /usr/share/kicad/template/sym-lib-table /root/.config/kicad/10.0/sym-lib-table 2>/dev/null || true \
    # the repository mounts at /work; register its custom footprint library
    && sed -i '$i\  (lib (name gateway_fp)(type KiCad)(uri /work/hardware/circuits/lib/gateway_fp.pretty)(options "")(descr "project footprints"))' \
       /root/.config/kicad/10.0/fp-lib-table /root/.config/kicad/fp-lib-table

# kinet2pcb 1.1.4 doesn't strip quotes from the KiCad 10 fp-lib-table
# (which uses quoted attribute values); remove quotes so library lookup works
COPY docker/eda/fix_fp_lib_table.py /tmp/fix_fp_lib_table.py
RUN python3 /tmp/fix_fp_lib_table.py && rm /tmp/fix_fp_lib_table.py

# fastroute: published release binary, checksum from the release's SHA256SUMS.txt.
ARG FASTROUTE_VERSION=0.1.14
ARG FASTROUTE_SHA256=079a109f76d84836e7d7a54519e75759dcab9baacc9c58b4224b027b852e49c6
RUN curl -fsSL -o /tmp/fastroute.tar.gz \
       "https://github.com/parisxmas/fastroute/releases/download/v${FASTROUTE_VERSION}/fastroute-${FASTROUTE_VERSION}-linux-x64.tar.gz" \
    && echo "${FASTROUTE_SHA256}  /tmp/fastroute.tar.gz" | sha256sum -c - \
    && tar -xzf /tmp/fastroute.tar.gz -C /tmp \
    && install -m 0755 "/tmp/fastroute-${FASTROUTE_VERSION}-linux-x64/fastroute" /usr/local/bin/fastroute \
    && rm -rf /tmp/fastroute* \
    && fastroute --help | head -1

WORKDIR /work
ENTRYPOINT ["/bin/bash", "-c"]
