from flask import Flask, request, session, render_template, abort, redirect
from flask_mysqldb import MySQL
import os, logging

app = Flask(__name__)

app.secret_key = os.urandom(12).hex()
app.debug = True

mysql = MySQL(app)


def mysql_connection():
    connection = mysql.connect
    return connection


def mysql_config():
    """creating mysql connection and initialize at single place"""
    app.config['MYSQL_HOST'] = session['host']
    app.config['MYSQL_USER'] = session['user']
    app.config['MYSQL_PASSWORD'] = session['password']
    app.config['MYSQL_DB'] = session['database']
    app.config['MYSQL_PORT'] = 3306


def query(connection, query):
    cursor = connection.cursor()
    cursor.execute(query)
    connection.commit()
    data = cursor.fetchall()
    return data


@app.route("/", methods=["GET", "POST"])
def home():
    """when user go to application server directly, redirects to PyAdminer"""
    return redirect('/py_adminer')


@app.route("/py_adminer", methods=["GET", "POST"])
def py_admin():
    """PyAdminer provide you web interface to manage your database.
    you can execute mysql queries and view output in web tables format.
    most useful for those users who are familiar with php adminer tool.
    it works the same way for python."""
    databases = []
    tables = []
    login = False
    if 'pass' in session:
        login = True

    if request.method == "POST" or 'pass' in session:
        if 'pass' not in session:
            session['system'] = request.form.get('system', 'mysql')
            session['host'] = request.form.get('server', 'localhost')
            session['user'] = request.form.get('username')
            session['password'] = request.form.get('password')
            session['database'] = request.form.get('database')
            mysql_config()
            return redirect('/py_adminer?database=' + request.form.get('database'))
    # for mysql engine connection
    if 'system' in session and session['system'] == 'mysql':
        try:
            connection = mysql_connection()
        except ConnectionError as ex:
            return redirect('/')
        if request.args.get('database'):
            database = request.args.get('database')
            query(connection, "use "+str(database)+';')
            tables = query(connection, "SHOW TABLES;")
        databases = query(connection, "SHOW DATABASES")

        # required in case query fails
        if databases:
            session['pass'] = True
            login = True

    return render_template('py_adminer.html', py_admin_url="/py_adminer", login=login, databases=databases,
                           tables=tables)


if __name__ == '__main__':
    app.logger.setLevel(logging.INFO)
    app.run(debug=True, host="0.0.0.0", port=5000)
