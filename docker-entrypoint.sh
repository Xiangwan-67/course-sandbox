#!/bin/sh
set -e

export MYSQL_HOST="${MYSQL_HOST:-db}"
export MYSQL_PORT="${MYSQL_PORT:-3306}"

# 仅在使用 MySQL 时等待端口就绪（本地 SQLite 不设 MYSQL_HOST 则跳过）
if [ -n "${MYSQL_HOST:-}" ]; then
  echo "Waiting for MySQL at ${MYSQL_HOST}:${MYSQL_PORT}..."
  i=0
  while [ "$i" -lt 60 ]; do
    if python -c "
import os, socket
h = os.environ.get('MYSQL_HOST', 'db')
p = int(os.environ.get('MYSQL_PORT', '3306'))
s = socket.socket()
s.settimeout(2)
s.connect((h, p))
s.close()
" 2>/dev/null; then
      echo "MySQL is reachable."
      break
    fi
    i=$((i + 1))
    sleep 2
  done
fi

python sandbox_site/manage.py migrate
python sandbox_site/manage.py collectstatic --noinput

exec gunicorn sandbox_site.wsgi:application --bind 0.0.0.0:8000 --workers 4 --timeout 120
