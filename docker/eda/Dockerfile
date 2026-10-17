# EDA toolchain: KiCad 10.0.6 (kicad-cli + pcbnew Python bindings) via the
# official kicad/kicad:10.0 image (Debian trixie, amd64 emulation on arm64),
# SKiDL for circuit authoring, kinet2pcb for netlist-to-board conversion and
# Freerouting 2.5.0 on Java 25 for `layout.py route`.
FROM --platform=linux/amd64 eclipse-temurin:25.0.4.1_1-jre AS jre

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
       shapely==2.1.1

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

COPY --from=jre /opt/java/openjdk /opt/java/openjdk
ENV JAVA_HOME=/opt/java/openjdk \
    PATH=/opt/java/openjdk/bin:$PATH \
    FREEROUTING_JAR=/opt/freerouting.jar
RUN curl -fsSL -o /opt/freerouting.jar \
       https://github.com/freerouting/freerouting/releases/download/v2.5.0/freerouting-2.5.0.jar \
    && echo "f6f51bb02245e8e717f9359bd260cc9c5c0b1bc0acc8b7cb2cd5b8ffeb5de3c7  /opt/freerouting.jar" \
       | sha256sum -c -

WORKDIR /work
ENTRYPOINT ["/bin/bash", "-c"]
