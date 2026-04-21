import os

# 仅在使用 MySQL 时加载 PyMySQL（本地默认 SQLite 不依赖）
if os.environ.get("MYSQL_HOST", "").strip():
    import pymysql

    pymysql.install_as_MySQLdb()
