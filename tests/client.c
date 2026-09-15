#include <mysql.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(void) {
  MYSQL *connection = mysql_init(NULL);
  enum mysql_ssl_mode ssl_mode = SSL_MODE_REQUIRED;
  mysql_options(connection, MYSQL_READ_DEFAULT_FILE, "/run/secrets/app.cnf");
  mysql_options(connection, MYSQL_OPT_SSL_MODE, &ssl_mode);
  if (!mysql_real_connect(connection, "127.0.0.1", NULL, NULL, "app_db", 3306,
                          NULL, 0)) {
    fprintf(stderr, "connection failed: %s\n", mysql_error(connection));
    return 1;
  }
  if (!mysql_get_ssl_cipher(connection)) return 2;
  MYSQL_STMT *statement = mysql_stmt_init(connection);
  const char *sql = "SELECT ? + ?";
  int32_t left = 17, right = 25, result = 0;
  MYSQL_BIND parameters[2] = {0}, output = {0};
  parameters[0].buffer_type = parameters[1].buffer_type = MYSQL_TYPE_LONG;
  parameters[0].buffer = &left;
  parameters[1].buffer = &right;
  output.buffer_type = MYSQL_TYPE_LONG;
  output.buffer = &result;
  if (mysql_stmt_prepare(statement, sql, strlen(sql)) ||
      mysql_stmt_bind_param(statement, parameters) ||
      mysql_stmt_execute(statement) || mysql_stmt_bind_result(statement, &output) ||
      mysql_stmt_fetch(statement) || result != 42) {
    fprintf(stderr, "prepared statement failed: %s\n", mysql_stmt_error(statement));
    return 3;
  }
  mysql_stmt_close(statement);
  mysql_close(connection);
  puts("TLS connection and binary-protocol prepared statement passed");
  return 0;
}
