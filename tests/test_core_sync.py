from contextlib import AbstractContextManager, contextmanager
from typing import Callable
from unittest.mock import MagicMock, Mock, call

from pytest import raises

from dependency_injection.core import (
    Dependency,
    ImmutableContainer,
    ScopedContainers,
    create_resolver,
    create_scoped_resolver,
)
from tests.helpers import A_INST, B_INST, A, B, C


class TestResolver:
    def test_calls_container_types_matcher(self):
        factory = Mock(Callable, name='factory')
        provided_type = Mock(type, name='provided-type')
        required_type = Mock(type, name='required-type')
        types_matcher = Mock(Callable, name='types-matcher')
        container = ImmutableContainer(
            {'a': Dependency('a', provided_type, {}, factory)},
            types_matcher,
        )

        with create_resolver(container) as resolver:
            value = resolver.resolve('a', required_type)

        assert value is factory.return_value
        assert types_matcher.mock_calls == [call(provided_type, required_type)]

    def test_provides_simple(self):
        a_factory = Mock(Callable, name='a-factory', return_value=A_INST)
        container = ImmutableContainer(
            {'a': Dependency('a', A, requires={}, factory=a_factory)}
        )

        with create_resolver(container) as resolver:
            assert resolver.resolve('a', A) is A_INST
        assert a_factory.mock_calls == [call()]

    def test_created_value_been_memoized_v1(self):
        container = ImmutableContainer(
            {'a': Dependency('a', A, {}, factory=A)}
        )
        with create_resolver(container) as resolver:
            a1 = resolver.resolve('a', A)
            a2 = resolver.resolve('a', A)
            assert a1 is a2

    def test_created_value_been_memoized_v2(self):
        a_factory = Mock(Callable, name='a-factory')
        container = ImmutableContainer(
            {'a': Dependency('a', A, {}, factory=a_factory)}
        )
        with create_resolver(container) as resolver:
            a1 = resolver.resolve('a', A)
            a2 = resolver.resolve('a', A)
            assert a_factory.mock_calls == [call()]
            assert a1 is a2 is a_factory.return_value

    def test_provides_with_deps(self):
        a_factory = Mock(Callable, name='a-factory', return_value=A_INST)
        b_factory = Mock(Callable, name='b-factory', return_value=B_INST)
        c_factory = Mock(Callable, name='c-factory', wraps=C)
        container = ImmutableContainer(
            {
                'a': Dependency('a', A, {}, factory=a_factory),
                'b': Dependency('b', B, {}, factory=b_factory),
                'c': Dependency(
                    'c',
                    C,
                    {'a': ('a', A), 'b': ('b', B)},
                    factory=c_factory,
                ),
            }
        )

        with create_resolver(container) as resolver:
            c_provided = resolver.resolve('c', C)
            assert isinstance(c_provided, C)
            assert c_provided.a is A_INST
            assert c_provided.b is B_INST
            assert a_factory.mock_calls == [call()]
            assert b_factory.mock_calls == [call()]
            assert c_factory.mock_calls == [call(a=A_INST, b=B_INST)]

    def test_provides_dep_by_custom_arg_name(self):
        def c_factory(*, a_arg, b_arg):
            return C(a_arg, b_arg)

        c_factory_mock = Mock(Callable, wraps=c_factory, name='c-factory')
        container = ImmutableContainer(
            {
                'a': Dependency('a', A, {}, factory=lambda: A_INST),
                'b': Dependency('b', B, {}, factory=lambda: B_INST),
                'c': Dependency(
                    'c',
                    C,
                    {'a_arg': ('a', A), 'b_arg': ('b', B)},
                    factory=c_factory_mock,
                ),
            }
        )

        with create_resolver(container) as resolver:
            c_inst = resolver.resolve('c', C)
            assert c_inst.a is A_INST
            assert c_inst.b is B_INST
            assert c_factory_mock.mock_calls == [
                call(a_arg=A_INST, b_arg=B_INST)
            ]

    def test_context_manager_factory(self):
        a_cm = MagicMock(AbstractContextManager, name='a-cm')
        a_cm.__enter__.return_value = A_INST
        a_cm_factory = Mock(Callable, name='a-factory', return_value=a_cm)
        container = ImmutableContainer(
            {'a': Dependency('a', A, {}, a_cm_factory, context_manager=True)}
        )

        with create_resolver(container) as resolver:
            a = resolver.resolve('a', A)
            assert a is A_INST
            assert a_cm_factory.mock_calls == [call()]
            # `ExitStack` calls context managers methods like
            # `type(cm).__exit__(cm)`, so calls are registered with explicit self
            # argument, but it doesn't really affects anything except how do we
            # verify them
            assert a_cm.mock_calls == [call.__enter__(a_cm)]

        assert a_cm.mock_calls == [
            call.__enter__(a_cm),
            # Verify context manager being finalized after exiting resolver's scope
            call.__exit__(a_cm, None, None, None),
        ]

    def test_context_manager_as_sub_dep(self):
        @contextmanager
        def a_cm():
            yield A_INST

        container = ImmutableContainer(
            {
                'a': Dependency(
                    'a', A, {}, factory=a_cm, context_manager=True
                ),
                'b': Dependency('b', B, {}, factory=lambda: B_INST),
                'c': Dependency(
                    'c',
                    C,
                    {'a': ('a', A), 'b': ('b', B)},
                    factory=Mock(Callable, wraps=C),
                ),
            }
        )

        with create_resolver(container) as resolver:
            c = resolver.resolve('c', C)
            assert c.a is A_INST
            assert c.b is B_INST

    def test_there_is_recursion_error_TODO(self):
        a_factory = Mock(Callable, name='a-factory', return_value=A_INST)
        b_factory = Mock(Callable, name='b-factory', return_value=B_INST)
        container = ImmutableContainer(
            {
                'a': Dependency('a', A, {'b': ('b', B)}, a_factory),
                'b': Dependency('b', B, {'a': ('a', A)}, b_factory),
            }
        )

        with create_resolver(container) as resolver:
            with raises(RecursionError):
                resolver.resolve('a', A)


class TestScopedResolver:
    SCOPES_ORDER = ['root', 'app', 'handler']

    def test_deliveries_sub_deps(self):
        """
        - ROOT SCOPE
          * CONFIG
          - APP SCOPE
            * DB(CONFIG)
            * CACHE(CONFIG)
            - HANDLER SCOPE
              * TRANSACTION(DB)
              * FOO_CTRL(TRANSACTION)
              * BAR_CTRL(TRANSACTION, CACHE)
        """

        class Cfg:
            pass

        class DB:
            pass

        class Cache:
            pass

        class Transaction:
            pass

        class FooCtrl:
            pass

        class BarCtrl:
            pass

        # Root scope factories
        cfg_factory = Mock(name='cfg-factory')

        # App scope factories
        db_factory = Mock(name='db-factory')
        cache_factory = Mock(name='cache-factory')

        # Handler scope factories
        transaction_factory = Mock(name='transaction-factory')
        foo_ctrl_factory = Mock(name='foo-ctrl-factory')
        bar_ctrl_factory = Mock(name='bar-ctrl-factory')

        scoped_containers = ScopedContainers(
            self.SCOPES_ORDER,
            {
                'root': ImmutableContainer(
                    {'cfg': Dependency('cfg', Cfg, {}, cfg_factory)}
                ),
                'app': ImmutableContainer(
                    {
                        'db': Dependency(
                            'db', DB, {'cfg': ('cfg', Cfg)}, db_factory
                        ),
                        'cache': Dependency(
                            'cache',
                            Cache,
                            {'cfg': ('cfg', Cfg)},
                            cache_factory,
                        ),
                    }
                ),
                'handler': ImmutableContainer(
                    {
                        'transaction': Dependency(
                            'transaction',
                            Transaction,
                            {'db': ('db', DB)},
                            transaction_factory,
                        ),
                        'foo_ctrl': Dependency(
                            'foo_ctrl',
                            FooCtrl,
                            {'transaction': ('transaction', Transaction)},
                            foo_ctrl_factory,
                        ),
                        'bar_ctrl': Dependency(
                            'bar_ctrl',
                            BarCtrl,
                            {
                                'transaction': ('transaction', Transaction),
                                'cache': ('cache', Cache),
                            },
                            bar_ctrl_factory,
                        ),
                    }
                ),
            },
        )

        with create_scoped_resolver(scoped_containers) as root_resolver:
            with root_resolver.next_scope() as app_resolver:
                with app_resolver.next_scope() as handler_resolver:
                    foo_ctrl = handler_resolver.resolve('foo_ctrl', FooCtrl)
                    bar_ctrl = handler_resolver.resolve('bar_ctrl', BarCtrl)

        assert foo_ctrl is foo_ctrl_factory.return_value
        assert bar_ctrl is bar_ctrl_factory.return_value

        assert foo_ctrl_factory.mock_calls == [
            call(transaction=transaction_factory.return_value)
        ]
        assert bar_ctrl_factory.mock_calls == [
            call(
                transaction=transaction_factory.return_value,
                cache=cache_factory.return_value,
            )
        ]
        assert transaction_factory.mock_calls == [
            call(db=db_factory.return_value)
        ]

        assert db_factory.mock_calls == [call(cfg=cfg_factory.return_value)]
        assert cache_factory.mock_calls == [call(cfg=cfg_factory.return_value)]

        assert cfg_factory.mock_calls == [call()]
