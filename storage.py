from contextlib import contextmanager
from sqlite3 import Connection
from typing import Iterator


@contextmanager
def write_transaction(connection: Connection) -> Iterator[None]:
    connection.execute('BEGIN IMMEDIATE')
    try:
        yield
        connection.execute('COMMIT')
    except BaseException:
        if connection.in_transaction:
            connection.execute('ROLLBACK')
        raise


def is_record_number(value: object) -> bool:
    return type(value) is int and 0 < value < 2 ** 63
