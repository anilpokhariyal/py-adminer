from pyadminer.db import format_mysql_error


def test_format_mysql_error_tuple_exception():
    class E(Exception):
        pass

    err = E(1055, "not in GROUP BY")
    assert "1055" in format_mysql_error(err)
    assert "GROUP BY" in format_mysql_error(err)


def test_format_mysql_error_string_tuple():
    s = '(1055, "Expression #2 of SELECT list is not in GROUP BY")'
    out = format_mysql_error(s)
    assert "1055" in out
    assert "GROUP BY" in out


def test_format_mysql_error_plain_string():
    assert format_mysql_error("something went wrong") == "something went wrong"
