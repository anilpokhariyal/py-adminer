from flask import Flask, request, session, render_template, abort, redirect, jsonify
from flask_mysqldb import MySQL, MySQLdb
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
    cursor = connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute(query)
    connection.commit()
    return cursor


@app.route("/", methods=["GET", "POST"])
def home():
    """when user go to application server directly, redirects to PyAdminer"""
    return redirect('/py_adminer')


@app.route("/create_database", methods=["POST"])
def create_database():
    """create/alter database"""
    if 'system' in session and session['system'] == 'mysql':
        try:
            connection = mysql_connection()
        except ConnectionError as ex:
            return redirect('/')

        db_name = request.form.get('database_name')
        collation = eval(request.form.get('database_collection'))
        create_db = "CREATE DATABASE " + db_name
        if collation:
            create_db += " CHARACTER SET " + collation[1] + " COLLATE " + collation[0] + ";"
        query(connection, create_db)

        # alter database and it's tables
        alter_db = request.form.get('alter_db_name', None)
        if alter_db:
            query(connection, "use information_schema;")
            table_query = "SELECT TABLE_NAME FROM TABLES WHERE TABLE_SCHEMA = '" + alter_db + "'"
            tables = query(connection, table_query)

            query(connection, "use " + alter_db + ";")
            for table in tables:
                query(connection,
                      "RENAME TABLE " + table['TABLE_NAME'] + " TO `" + db_name + "`.`" + table['TABLE_NAME'] + "`;")
            query(connection, "DROP DATABASE " + alter_db + ";")

        return redirect('/')


@app.route("/drop_database", methods=["POST"])
def drop_database():
    """drop database"""
    if 'system' in session and session['system'] == 'mysql':
        try:
            connection = mysql_connection()
        except ConnectionError as ex:
            return redirect('/')

        databases = request.form.getlist('db_name')
        for database in databases:
            query(connection, "DROP DATABASE " + database + ";")

        return redirect('/')


@app.route("/create_table", methods=["POST"])
def create_table():
    """create table in selected database"""
    database = request.form.get("database")
    table_name = request.form.get('table_name')
    # for mysql engine connection
    if 'system' in session and session['system'] == 'mysql':
        try:
            connection = mysql_connection()
        except ConnectionError as ex:
            return redirect('/')

        # use databases and create table
        try:
            query(connection, "use " + database + ";")
            create_query = request.form.get('create_table_query')
            query(connection, create_query)
        except (MySQLdb.Error, MySQLdb.Warning) as e:
            print(e)

    return redirect('/py_adminer?database='+database+'&table='+table_name)


@app.route("/py_adminer", methods=["GET", "POST"])
def py_admin():
    """PyAdminer provide you web interface to manage your database.
    you can execute mysql queries and view output in web tables format.
    most useful for those users who are familiar with php adminer tool.
    it works the same way for python."""
    databases = []
    db_collations = {}
    tables = []
    table_structure = []
    table_data = []
    table_columns = []
    db_engines = []
    column_types = []
    mysql_version = 0
    login = False
    selected_db = None
    selected_table = None
    action = request.args.get('action', None)
    create = request.args.get('create', None)
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

        # fetching databases information
        query(connection, "use information_schema;")
        db_query = "SELECT SCHEMATA.SCHEMA_NAME,SCHEMATA.DEFAULT_COLLATION_NAME," \
                   "count(TABLES.TABLE_NAME) as TABLES_COUNT,sum(TABLES.DATA_LENGTH) as SCHEMA_SIZE FROM SCHEMATA" \
                   " LEFT JOIN TABLES ON TABLES.TABLE_SCHEMA = SCHEMATA.SCHEMA_NAME " \
                   "GROUP BY SCHEMATA.SCHEMA_NAME"
        databases = query(connection, db_query)

        # fetching mysql version
        mysql_version = query(connection, "select version() as version;")
        for version in mysql_version:
            mysql_version = version

        # setting database name for alter
        if request.args.get('database') and create:
            database = str(request.args.get('database'))
            selected_db = database

        # options of collation and engine for creating database or table
        if create:
            # fetching all collations for database collection type on UI
            query(connection, "use information_schema;")
            all_collations = query(connection, "SELECT * FROM COLLATIONS ORDER BY SORTLEN ASC")
            for collation in all_collations:
                if collation['CHARACTER_SET_NAME'] in db_collations:
                    db_collations[collation['CHARACTER_SET_NAME']].append(collation)
                else:
                    db_collations[collation['CHARACTER_SET_NAME']] = [collation, ]

            if create == 'table':
                # for create table
                query(connection, "use information_schema;")
                db_engines = query(connection, "SELECT * FROM ENGINES")
                column_types = query(connection, "SELECT * FROM COLLATIONS ORDER BY SORTLEN ASC")
                for collation in all_collations:
                    if collation['CHARACTER_SET_NAME'] in db_collations:
                        db_collations[collation['CHARACTER_SET_NAME']].append(collation)
                    else:
                        db_collations[collation['CHARACTER_SET_NAME']] = [collation, ]

        # fetching tables from selected database
        if request.args.get('database') and not create:
            database = str(request.args.get('database'))
            selected_db = database
            query(connection, "use information_schema;")
            table_query = "SELECT TABLE_NAME, ENGINE,TABLE_ROWS, DATA_LENGTH, INDEX_LENGTH," \
                          " AUTO_INCREMENT, TABLE_COLLATION, TABLE_COMMENT " \
                          " FROM TABLES WHERE TABLE_SCHEMA = '" + database + "'"
            tables = query(connection, table_query)

        # fetching table data and structure
        if selected_db and request.args.get('table') and not action:
            table_name = str(request.args.get('table'))
            selected_table = table_name
            query(connection, "use information_schema;")
            structure_query = "SELECT COLUMN_NAME,IS_NULLABLE,COLUMN_DEFAULT,COLUMN_TYPE,COLUMN_KEY,EXTRA,COLUMN_COMMENT FROM COLUMNS " \
                              " WHERE TABLE_NAME='" + table_name + "' AND TABLE_SCHEMA='" + selected_db + "' ORDER BY ORDINAL_POSITION ASC"
            table_structure = query(connection, structure_query)
        # todo index and foreign keys

        # fetching table data
        if selected_db and request.args.get('table') and action:
            table_name = str(request.args.get('table'))
            selected_table = table_name
            limit = 1000
            query(connection, "use information_schema;")
            col_query = "SELECT COLUMN_NAME FROM COLUMNS " \
                        " WHERE TABLE_NAME='" + table_name + "' " \
                                                             " AND TABLE_SCHEMA='" + selected_db + "'"
            table_columns = query(connection, col_query)
            query(connection, "use " + selected_db)
            data_query = "SELECT * FROM " + selected_table + " LIMIT " + str(limit)
            table_data = query(connection, data_query)

        # required in case query fails
        if databases:
            session['pass'] = True
            login = True

    return render_template('py_adminer.html', py_admin_url="/py_adminer", login=login, databases=databases,
                           mysql_version=mysql_version, create=create, action=action,
                           tables=tables, table_structure=table_structure, db_engines=db_engines,
                           table_data=table_data, table_columns=table_columns, db_collations=db_collations,
                           selected_db=selected_db, selected_table=selected_table)


if __name__ == '__main__':
    app.logger.setLevel(logging.INFO)
    app.run(debug=True, host="0.0.0.0", port=5000)
