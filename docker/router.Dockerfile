FROM morrowsql:8.4.11-1
COPY docker/router-entrypoint.sh /router-entrypoint.sh
RUN chmod 0755 /router-entrypoint.sh \
    && groupadd --gid 999 mysqlrouter \
    && useradd --uid 999 --gid 999 --home-dir /tmp/mysqlrouter mysqlrouter
USER mysqlrouter
ENTRYPOINT ["/router-entrypoint.sh"]
CMD ["mysqlrouter"]
