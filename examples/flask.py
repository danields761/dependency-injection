from collections import Callable
from enum import IntEnum

import flask
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.engine import Engine

from dependency_injection import SyncMutableContainer


class Scope(IntEnum):
    app = 0
    handler = 1


di = SyncMutableContainer()
di.provides_at_scope(Scope.app, 'engine', Engine, create_engine)
di.provides_at_scope(
    Scope.app, 'session_maker', Callable[[Engine], Session], sessionmaker
)
di.provides_at_scope(
    Scope.handler,
    'session',
    Session,
    lambda session_maker: session_maker(),
    session_maker=('session_maker', Callable[[Engine], Session]),
)

app = flask.Flask('example')
