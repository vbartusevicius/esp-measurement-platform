# CadQuery enclosure generation + the PCB/enclosure fit checker. cadquery
# 2.8.0 pulls cadquery-ocp 7.9.3.1 which ships manylinux aarch64 wheels, so
# this image builds natively on arm64 hosts.
FROM python:3.13.9-slim-trixie

RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 libxrender1 libxcursor1 libxext6 libxi6 \
        libxft2 libxinerama1 libxmu6 libxrandr2 libxt6 libxxf86vm1 \
        librsvg2-bin libosmesa6 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir cadquery==2.8.0 pyyaml==6.0.3 pytest==8.4.2

WORKDIR /work
ENTRYPOINT ["/bin/bash", "-lc"]
