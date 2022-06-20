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
    app.config["MYSQL_HOST"] = session["host"]
    app.config["MYSQL_USER"] = session["user"]
    app.config["MYSQL_PASSWORD"] = session["password"]
    app.config["MYSQL_DB"] = session["database"]
    app.config["MYSQL_PORT"] = 3306


def query(connection, query):
    error = None
    try:
        cursor = connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute(query)
        connection.commit()
        return cursor
    except MySQLdb._exceptions.OperationalError as err:
        app.logger.error("MYSQL Connection Error: {}".format(err))
        error = err
    except MySQLdb._exceptions.ProgrammingError as err:
        app.logger.error("MYSQL Programming Error: {}".format(err))
        error = err
    except Exception as err:
        app.logger.error("Error: {}".format(err))
        error = err

    session["error"] = str(error)


@app.route("/", methods=["GET", "POST"])
def home():
    """when user go to application server directly, redirects to PyAdminer"""
    return redirect("/py_adminer")


@app.route("/create_database", methods=["POST"])
def create_database():
    """create/alter database"""
    if "system" in session and session["system"] == "mysql":
        try:
            connection = mysql_connection()
        except ConnectionError as ex:
            return redirect("/")

        db_name = request.form.get("database_name")
        alter_db = request.form.get("alter_db_name", None)
        if db_name != alter_db:
            collation = eval(request.form.get("database_collection"))
            create_db = "CREATE DATABASE " + db_name
            if collation:
                create_db += (
                    " CHARACTER SET " + collation[1] + " COLLATE " + collation[0] + ";"
                )
            query(connection, create_db)

            # alter database and it's tables
            if alter_db and alter_db != "None":
                query(connection, "use information_schema;")
                table_query = (
                    "SELECT TABLE_NAME FROM TABLES WHERE TABLE_SCHEMA = '"
                    + alter_db
                    + "'"
                )
                tables = query(connection, table_query)

                query(connection, "use " + alter_db + ";")
                for table in tables:
                    query(
                        connection,
                        "RENAME TABLE "
                        + table["TABLE_NAME"]
                        + " TO `"
                        + db_name
                        + "`.`"
                        + table["TABLE_NAME"]
                        + "`;",
                    )
                query(connection, "DROP DATABASE " + alter_db + ";")

        return redirect("/")


@app.route("/drop_database", methods=["POST"])
def drop_database():
    """drop database"""
    if "system" in session and session["system"] == "mysql":
        try:
            connection = mysql_connection()
        except ConnectionError as ex:
            return redirect("/")

        databases = request.form.getlist("db_name")
        for database in databases:
            query(connection, "DROP DATABASE " + database + ";")

        return redirect("/")


@app.route("/create_table", methods=["POST"])
def create_table():
    """create table in selected database"""
    database = request.form.get("database")
    table_name = request.form.get("table_name")
    # for mysql engine connection
    if "system" in session and session["system"] == "mysql":
        try:
            connection = mysql_connection()
        except ConnectionError as ex:
            return redirect("/")

        # use databases and create table
        try:
            query(connection, "use " + database + ";")
            create_query = request.form.get("create_table_query")
            query(connection, create_query)
        except (MySQLdb.Error, MySQLdb.Warning) as e:
            print(e)

    return redirect("/py_adminer?database=" + database + "&table=" + table_name)


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
    search_by = []
    expression = []
    search_value = []
    data_query = ""
    order_by = ""
    order = "asc"
    limit = 1000
    table_columns = []
    db_engines = []
    column_types = []
    mysql_version = 0
    login = False
    selected_db = None
    selected_table = None
    action = request.values.get("action", None)
    create = request.values.get("create", None)
    sql_panel = request.values.get("sql_panel", None)
    if not sql_panel:
        sql_panel = request.values.get("sql_panel", None)
    sql_query = request.values.get("sql_query", None)
    query_output = []
    if "pass" in session:
        login = True

    if request.method == "POST" or "pass" in session:
        if "pass" not in session:
            session["system"] = request.values.get("system", "mysql")
            session["host"] = request.values.get("server", "localhost")
            session["user"] = request.values.get("username")
            session["password"] = request.values.get("password")
            session["database"] = request.values.get("database")
            mysql_config()
            return redirect("/py_adminer?database=" + request.values.get("database"))
    # for mysql engine connection
    if "system" in session and session["system"] == "mysql":
        try:
            connection = mysql_connection()
        except ConnectionError as ex:
            return redirect("/")

        # fetching databases information
        query(connection, "use information_schema;")
        db_query = (
            "SELECT SCHEMATA.SCHEMA_NAME,SCHEMATA.DEFAULT_COLLATION_NAME,"
            "count(TABLES.TABLE_NAME) as TABLES_COUNT,sum(TABLES.DATA_LENGTH) as SCHEMA_SIZE FROM SCHEMATA"
            " LEFT JOIN TABLES ON TABLES.TABLE_SCHEMA = SCHEMATA.SCHEMA_NAME "
            "GROUP BY SCHEMATA.SCHEMA_NAME"
        )
        databases = query(connection, db_query)

        # fetching mysql version
        mysql_version = query(connection, "select version() as version;")
        for version in mysql_version:
            mysql_version = version

        # setting database name for alter
        if request.args.get("database") and create:
            database = str(request.args.get("database"))
            selected_db = database

        # options of collation and engine for creating database or table
        if create or action == "alter":
            # fetching all collations for database collection type on UI
            query(connection, "use information_schema;")
            all_collations = query(
                connection, "SELECT * FROM COLLATIONS ORDER BY SORTLEN ASC"
            )
            for collation in all_collations:
                if collation["CHARACTER_SET_NAME"] in db_collations:
                    db_collations[collation["CHARACTER_SET_NAME"]].append(collation)
                else:
                    db_collations[collation["CHARACTER_SET_NAME"]] = [
                        collation,
                    ]

            # for create table
            query(connection, "use information_schema;")
            db_engines = query(connection, "SELECT * FROM ENGINES")
            column_types = query(
                connection, "SELECT * FROM COLLATIONS ORDER BY SORTLEN ASC"
            )

        # fetching tables from selected database if not create request or sql_panel
        if request.args.get("database") and not create:
            database = str(request.args.get("database"))
            selected_db = database
            query(connection, "use information_schema;")
            table_query = (
                "SELECT TABLE_NAME, ENGINE,TABLE_ROWS, DATA_LENGTH, INDEX_LENGTH,"
                " AUTO_INCREMENT, TABLE_COLLATION, TABLE_COMMENT "
                " FROM TABLES WHERE TABLE_SCHEMA = '" + database + "'"
            )
            tables = query(connection, table_query)

        # fetching table data and structure
        if (
            selected_db
            and request.args.get("table")
            and (not action or action == "alter")
        ):
            table_name = str(request.args.get("table"))
            selected_table = table_name
            query(connection, "use information_schema;")
            structure_query = (
                "SELECT COLUMN_NAME,IS_NULLABLE,COLUMN_DEFAULT,COLUMN_TYPE,COLUMN_KEY,EXTRA,COLUMN_COMMENT FROM COLUMNS "
                " WHERE TABLE_NAME='"
                + table_name
                + "' AND TABLE_SCHEMA='"
                + selected_db
                + "' ORDER BY ORDINAL_POSITION ASC"
            )
            table_structure = query(connection, structure_query)
        # todo index and foreign keys

        # fetching table data
        if selected_db and request.args.get("table") and action == "data":
            table_name = str(request.args.get("table"))
            selected_table = table_name
            search_by = request.form.getlist("search_by[]")
            expression = request.form.getlist("expression[]")
            search_value = request.form.getlist("search_value[]")
            where_query = ""
            for k in range(len(search_value)):
                if search_value[k]:
                    if k == 0:
                        where_query += " WHERE "
                    else:
                        where_query += " AND "
                    where_query += "`"+search_by[k]+"`" + expression[k] + '"' + search_value[k] + '"'

            limit = request.form.get("limit", 1000)
            order_by = request.form.get("order_by")
            order = request.form.get("order", "asc")
            query(connection, "use information_schema;")
            col_query = (
                "SELECT COLUMN_NAME FROM `COLUMNS` "
                "WHERE TABLE_NAME='" + table_name + "' "
                "AND TABLE_SCHEMA='" + selected_db + "' "
                "ORDER BY ORDINAL_POSITION ASC"
            )

            table_columns = query(connection, col_query)
            query(connection, "use " + selected_db)
            order_query = ""
            if order_by:
                order_query = " ORDER BY " + str(order_by) + " " + str(order)
            data_query = (
                "SELECT * FROM `"
                + str(selected_table)
                + "`"
                + where_query
                + order_query
                + " LIMIT "
                + str(limit)
            )

            table_data = query(connection, data_query)

        # for sql raw query execute
        if sql_query:
            query(connection, "use " + selected_db)
            query_output = query(connection, sql_query)

        # required in case query fails
        if databases:
            session["pass"] = True
            login = True

    # error display on py_adminer
    error = None
    if "error" in session:
        error = session["error"]
        session.pop("error")

    return render_template(
        "py_adminer.html",
        py_admin_url="/py_adminer",
        login=login,
        databases=databases,
        mysql_version=mysql_version,
        create=create,
        action=action,
        tables=tables,
        table_structure=table_structure,
        db_engines=db_engines,
        data_query=data_query,
        table_data=table_data,
        search_by=search_by,
        expression=expression,
        search_value=search_value,
        order_by=order_by,
        order=order,
        limit=limit,
        table_columns=table_columns,
        db_collations=db_collations,
        selected_db=selected_db,
        selected_table=selected_table,
        sql_panel=sql_panel,
        sql_query=sql_query,
        query_output=query_output,
        error=error,
    )


@app.route("/logout", methods=["GET", "POST"])
def logout():
    if "system" in session:
        session.pop("system")
    if "host" in session:
        session.pop("host")
    if "user" in session:
        session.pop("user")
    if "password" in session:
        session.pop("password")
    if "database" in session:
        session.pop("database")
    if "pass" in session:
        session.pop("pass")
    return redirect("/")


if __name__ == "__main__":
    app.logger.setLevel(logging.INFO)
    app.run(debug=True, host="0.0.0.0", port=5000)
