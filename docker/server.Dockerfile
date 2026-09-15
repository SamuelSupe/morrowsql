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
    && apt-get install -y --no-install-recommends ca-certificates libssl3t64 libaio1t64 \
       libnuma1 libncurses6 libtinfo6 libtirpc3t64 libstdc++6 libudev1 \
       libldap2 libsasl2-2 libcurl4t64 libevent-2.1-7t64 liblz4-1 libzstd1 \
       python3 util-linux \
    && dpkg-query -W > /usr/share/morrowsql-runtime-packages.tsv \
    && rm -rf /var/lib/apt/lists/* /etc/apt/apt.conf.d/99build-ca \
    && (groupmod --new-name mysql "$(getent group 27 | cut -d: -f1)" || groupadd --gid 27 mysql) && useradd --uid 27 --gid 27 --home-dir /var/lib/mysql mysql \
    && mkdir -p /var/lib/mysql /var/lib/mysql-files /var/run/mysqld /etc/my.cnf.d \
       /docker-entrypoint-initdb.d /usr/local/lib/morrowsql /usr/local/share/morrowsql \
    && chown mysql:mysql /var/lib/mysql /var/lib/mysql-files /var/run/mysqld
COPY build/stage/opt/morrowsql/ /opt/morrowsql/
COPY docker/entrypoint.sh /entrypoint.sh
COPY docker/bootstrap.py /usr/local/lib/morrowsql/bootstrap.py
COPY docker/my.cnf /etc/my.cnf
RUN chmod 0755 /entrypoint.sh \
    && printf '8.4.11-1\n' > /usr/local/share/morrowsql/version
ENV PATH=/opt/morrowsql/bin:/opt/morrowsql/sbin:$PATH
LABEL org.opencontainers.image.title="MorrowSQL" \
      org.opencontainers.image.version="8.4.11-1" \
      org.opencontainers.image.source="https://github.com/SamuelSupe/morrowsql"
EXPOSE 3306 33060 33061
STOPSIGNAL SIGTERM
ENTRYPOINT ["/entrypoint.sh"]
CMD ["mysqld"]
