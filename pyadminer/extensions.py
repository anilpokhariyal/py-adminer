from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_mysqldb import MySQL
from flask_wtf import CSRFProtect

mysql = MySQL()
csrf = CSRFProtect()

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
)
