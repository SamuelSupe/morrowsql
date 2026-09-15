FROM ubuntu:24.04@sha256:224a1869083a311ef3f13648a154ba79832fbef6364d31493642ca03082da254
ENV DEBIAN_FRONTEND=noninteractive
ADD --checksum=sha256:641de77d8f142cfd62a1a6f964ba67b20754d3337c480efb529d086075a06c9a https://snapshot.ubuntu.com/ubuntu/20260914T000000Z/pool/main/c/ca-certificates/ca-certificates_20240203_all.deb /tmp/ca-certificates.deb
RUN dpkg-deb -x /tmp/ca-certificates.deb /tmp/ca-bootstrap \
    && mkdir -p /etc/ssl/certs \
    && cat /tmp/ca-bootstrap/usr/share/ca-certificates/mozilla/*.crt > /etc/ssl/certs/ca-certificates.crt \
    && rm -rf /tmp/ca-bootstrap /tmp/ca-certificates.deb
RUN --mount=type=secret,id=build_ca,target=/run/secrets/build-ca.pem,mode=0444 \
    if [ -s /run/secrets/build-ca.pem ]; then printf 'Acquire::https::CaInfo "/run/secrets/build-ca.pem";\n' > /etc/apt/apt.conf.d/99build-ca; fi \
    && sed -i 's|^URIs:.*|URIs: https://snapshot.ubuntu.com/ubuntu/20260914T000000Z/|' /etc/apt/sources.list.d/ubuntu.sources \
    && apt-get -o Acquire::Check-Valid-Until=false -o APT::Update::Error-Mode=any update \
    && apt-get install -y --no-install-recommends \
       build-essential cmake ninja-build bison pkg-config git ca-certificates curl \
       libssl-dev libncurses-dev libtirpc-dev libaio-dev libudev-dev \
       libldap2-dev libsasl2-dev libcurl4-openssl-dev libevent-dev libssh-dev \
       libedit-dev libkrb5-dev zlib1g-dev libzstd-dev liblz4-dev uuid-dev \
       python3-dev python3-venv python3-pip perl libjson-perl libnuma-dev \
       patchelf rsync file jq xz-utils zstd \
    && dpkg-query -W > /build-packages.tsv \
    && rm -rf /var/lib/apt/lists/* /etc/apt/apt.conf.d/99build-ca
WORKDIR /workspace
