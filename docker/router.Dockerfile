FROM morrowsql:8.4.11-1
COPY docker/router-entrypoint.sh /router-entrypoint.sh
RUN chmod 0755 /router-entrypoint.sh
USER mysql
ENTRYPOINT ["/router-entrypoint.sh"]
CMD ["mysqlrouter"]
