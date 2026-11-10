"""Cooperative cancellation of this thread's read-only record queries only."""
from contextlib import contextmanager
from contextvars import ContextVar
_cancel=ContextVar('records_query_cancel',default=None)

@contextmanager
def cancellation_scope(event):
    token=_cancel.set(event)
    try:yield
    finally:_cancel.reset(token)

def attach_cancellation(connection):
    event=_cancel.get()
    if event is not None:
        if event.is_set():
            import sqlite3
            raise sqlite3.OperationalError('interrupted')
        connection.set_progress_handler(lambda:int(event.is_set()),10000)
