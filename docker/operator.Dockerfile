FROM morrowsql:8.4.11-1
COPY build/stage/opt/morrowsql-shell/ /opt/morrowsql-shell/
COPY docker/operator-requirements.txt /tmp/operator-requirements.txt
RUN --mount=type=secret,id=build_ca,target=/run/secrets/build-ca.pem,mode=0444 \
    if [ -s /run/secrets/build-ca.pem ]; then printf 'Acquire::https::CaInfo "/run/secrets/build-ca.pem";\n' > /etc/apt/apt.conf.d/99build-ca; fi \
    && apt-get -o Acquire::Check-Valid-Until=false -o APT::Update::Error-Mode=any update \
    && apt-get install -y --no-install-recommends libpython3.12t64 libssh-4 libedit2 python3-pip \
    && PIP_CERT="$(if [ -s /run/secrets/build-ca.pem ]; then echo /run/secrets/build-ca.pem; else echo /etc/ssl/certs/ca-certificates.crt; fi)" \
       pip3 install --no-cache-dir --target=/opt/operator-deps -r /tmp/operator-requirements.txt \
    && rm -rf /var/lib/apt/lists/* /etc/apt/apt.conf.d/99build-ca /tmp/operator-requirements.txt \
    && mkdir /mysqlsh && chown 2 /mysqlsh
COPY build/operator-code/mysqloperator/ /opt/operator/mysqloperator/
ENV PATH=/opt/morrowsql-shell/bin:$PATH \
    PYTHONPATH=/opt/operator:/opt/operator-deps \
    HOME=/mysqlsh \
    MYSQL_OPERATOR_DEFAULT_REPOSITORY=ghcr.io/samuelsupe/morrowsql/8.4.11-1
USER 2
ENTRYPOINT []
CMD ["mysqlsh", "--pym", "mysqloperator", "operator"]
