#!/bin/bash
set -e

# 앱 전용 DB 계정을 만들고 필요한 권한만 부여 (DCL)
mysql -uroot -p"$MYSQL_ROOT_PASSWORD" <<SQL
CREATE USER IF NOT EXISTS '${DB_USER}'@'%' IDENTIFIED BY '${DB_PASSWORD}';
GRANT SELECT, INSERT, UPDATE, DELETE ON bamboo.* TO '${DB_USER}'@'%';
FLUSH PRIVILEGES;
SQL
