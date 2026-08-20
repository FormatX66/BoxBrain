# syntax=docker/dockerfile:1.7@sha256:a57df69d0ea827fb7266491f2813635de6f17269be881f696fbfdf2d83dda33e
FROM debian:bookworm@sha256:813017f3d62be4b5891a7acca6a01bdcd4b8513daa81b1ab99d3a50385b26931

LABEL org.opencontainers.image.source="https://github.com/FormatX66/BoxBrain" \
      org.opencontainers.image.title="Aurum reproducible PC builder" \
      org.opencontainers.image.description="Prepared live-build and QEMU toolchain for Aurum PC"

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    TZ=UTC

COPY Projects/AurumBuild/packages.builder.txt /usr/share/aurum-builder/packages.builder.txt

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    set -eux; \
    rm -f /etc/apt/apt.conf.d/docker-clean; \
    printf 'Binary::apt::APT::Keep-Downloaded-Packages "true";\n' \
      > /etc/apt/apt.conf.d/99aurum-keep-downloads; \
    apt-get update; \
    sed -e '/^[[:space:]]*#/d' -e '/^[[:space:]]*$/d' \
      /usr/share/aurum-builder/packages.builder.txt \
      | xargs apt-get install -y --no-install-recommends; \
    dpkg-query -W -f='${Package}=${Version}\n' \
      | LC_ALL=C sort \
      > /usr/share/aurum-builder/dpkg-versions.txt; \
    lb --version; \
    qemu-system-x86_64 --version; \
    python3 --version; \
    rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
CMD ["/bin/bash"]
