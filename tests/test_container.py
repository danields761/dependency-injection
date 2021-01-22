from contextlib import contextmanager, asynccontextmanager
from enum import IntEnum
from typing import List, Union, Iterable, Sequence, Dict, Tuple
from unittest.mock import Mock, call, AsyncMock

from _pytest.mark import param
from pytest import raises, fixture, mark

from dependency_injection.container import (
    MutableContainer,
    provider_scope,
    provider_async_scope,
)


class Foo:
    pass


class Bar:
    def __init__(self, foo: Foo):
        self.foo = foo


class BarImpl(Bar):
    def __init__(self, foo: Foo, param: int):
        super().__init__(foo)
        self.param = param


class Scope(IntEnum):
    root = 0
    app = 1
    op = 2

    def __repr__(self):
        return f'{type(self).__name__}.{self.name}'


@fixture
def container():
    return MutableContainer(Scope)


@fixture
def root_provider(container):
    with provider_scope(container) as root_provider_:
        yield root_provider_


@fixture
def app_provider(root_provider):
    with provider_scope(root_provider, Scope.app) as app_provider_:
        yield app_provider_


@fixture
def op_provider(app_provider):
    with provider_scope(app_provider, Scope.op) as op_provider_:
        yield op_provider_


def test_container_root_scope_is_default(root_provider):
    assert root_provider.current_scope == Scope.root


class TestProvidersRegistration:
    def test_cant_register_non_instantiatable_without_factory(self, container):
        with raises(TypeError) as exc_info:
            container.provides('value', Tuple[int, float])
        assert str(exc_info.value) == (
            'Could not register provider for'
            'non-instantiatable type without factory'
        )

    def test_provides_class_registered_without_factory(
        self, container, app_provider
    ):
        container.provides('foo', Foo)
        foo = app_provider.provide('foo', Foo)
        assert isinstance(foo, Foo)

    def test_provides_at_scope(
        self, container, root_provider, app_provider, op_provider
    ):
        container.provides('foo', Foo)
        container.provides_at_scope(Scope.op, 'bar', Bar, foo=('foo', Foo))

        with raises(LookupError) as exc_info:
            app_provider.provide('bar', Bar)
        assert str(exc_info.value) == (
            'Dependency `bar: tests.test_container.Bar` lookup error: '
            'declared for future scope "Scope.op"'
        )

        bar = op_provider.provide('bar', Bar)
        assert isinstance(bar, Bar)
        assert bar.foo is op_provider.provide('foo', Foo)

    @mark.parametrize(
        'provides_type, requested_type, expects_value',
        [
            (BarImpl, Bar, BarImpl(Foo(), 100)),
            param(List[int], Iterable[int], [1, 2, 3], marks=mark.xfail),
            param(List[int], Sequence[int], [1, 2, 3], marks=mark.xfail),
            param(int, Union[str, int], 100, marks=mark.xfail),
            param(str, Union[str, int], 'test-string', marks=mark.xfail),
            param(
                List[int], List[Union[str, int]], [1, 2, 3], marks=mark.xfail
            ),
            param(
                List[str],
                List[Union[str, int]],
                ['v1', 'v2', 'v3'],
                marks=mark.xfail,
            ),
            param(
                List[int],
                Iterable[Union[str, int]],
                [1, 2, 3],
                marks=mark.xfail,
            ),
            param(
                List[str],
                Iterable[Union[str, int]],
                ['v1', 'v2', 'v3'],
                marks=mark.xfail,
            ),
            param(
                Dict[str, int],
                Iterable[Union[str, int]],
                {'k1': 1, 'k2': 2},
                marks=mark.xfail,
            ),
            param(
                Dict[str, str],
                Iterable[Union[str, int]],
                ['v1', 'v2', 'v3'],
                marks=mark.xfail,
            ),
            # TODO Protocol should be tested as well
        ],
    )
    def test_dependencies_could_be_resolved_requesting_supertypes(
        self,
        container,
        root_provider,
        app_provider,
        provides_type,
        requested_type,
        expects_value,
    ):
        container.provides('test_name', provides_type, lambda: expects_value)
        value = app_provider.provide('test_name', requested_type)
        assert value == expects_value

    @mark.parametrize(
        'provides_type, requested_type',
        [
            param(Iterable[int], List[int], marks=mark.xfail),
            param(List[Union[str, int]], List[int], marks=mark.xfail),
            param(List[Union[str, int]], Iterable[int], marks=mark.xfail),
            (Bar, BarImpl),
        ],
    )
    def test_cant_specialize_type_on_provide(
        self, container, app_provider, provides_type, requested_type
    ):
        container.provides('value', provides_type, lambda: 100)
        with raises(LookupError) as exc_info:
            app_provider.provide('value', requested_type)
        assert str(exc_info.value) == (
            'Dependency `value: tests.test_container.BarImpl` '
            'lookup error: provided type '
            'is `tests.test_container.Bar`'
        )


class TestProviderValuesFactoring:
    def test_provides_sync_value(self, container, app_provider):
        container.provides('value', int, lambda: 100)
        assert app_provider.provide('value', int) == 100

    def test_creates_value_once(self, container, root_provider):
        factory = Mock(name='factory')
        container.provides('value', Foo, factory)

        assert root_provider.provide('value', Foo) is factory.return_value
        assert root_provider.provide('value', Foo) is factory.return_value

        assert factory.mock_calls == [call()]

    def test_provides_cm_value(self, container):
        before_yield = Mock()
        after_yield = Mock()

        @contextmanager
        def cm_factory():
            before_yield()
            yield 100
            after_yield()

        container.provides('value', int, cm_factory)

        with provider_scope(container) as root_provider_:
            assert root_provider_.provide('value', int) == 100

        assert before_yield.mock_calls == [call()]
        assert after_yield.mock_calls == [call()]

    async def test_provides_async_value(self, container):
        async def value_factory():
            return 120

        container.provides('value', int, value_factory)

        async with provider_async_scope(container) as root_provider_:
            assert await root_provider_.provide('value', int) == 120

    async def test_provides_async_value_once(self, container):
        value_factory = AsyncMock(name='value-factory')
        container.provides('value', Foo, value_factory)

        async with provider_async_scope(container) as root_provider_:
            assert (
                await root_provider_.provide('value', Foo)
                == value_factory.return_value
            )
            assert (
                await root_provider_.provide('value', Foo)
                == value_factory.return_value
            )

        assert value_factory.mock_calls == [call()]

    async def test_provides_async_cm_value(self, container):
        before_yield = Mock()
        after_yield = Mock()

        @asynccontextmanager
        async def cm_factory():
            before_yield()
            yield 100
            after_yield()

        container.provides('value', int, cm_factory)

        async with provider_async_scope(container) as root_provider_:
            assert await root_provider_.provide('value', int) == 100

        assert before_yield.mock_calls == [call()]
        assert after_yield.mock_calls == [call()]


class TestScopingRules:
    @mark.xfail
    def test_provide_values_in_root_scope(self, root_provider):
        root_provider.provides('foo', Foo)

        with raises(RuntimeError) as exc_info:
            root_provider.provide('foo', Foo)
        assert str(exc_info.value) == 'Could not provide while in root scope'

    def test_cant_enter_indirect_scope(self, root_provider):
        with raises(RuntimeError) as exc_info:
            with provider_scope(root_provider, Scope.op):
                pass

        assert str(exc_info.value) == 'Could not enter indirect scope'

    def test_inherits_values_from_outer_scope(self, container, root_provider):
        foo_factory_mock = Mock(name='foo-factory')
        foo_mock = foo_factory_mock.return_value
        container.provides('foo', Foo, foo_factory_mock)
        with provider_scope(root_provider, Scope.app) as app_provider:
            with provider_scope(app_provider, Scope.op) as op_provider:
                assert op_provider.provide('foo', Foo) is foo_mock
            assert app_provider.provide('foo', Foo) is foo_mock

        # check factory called just once
        assert foo_factory_mock.mock_calls == [call()]

    @mark.xfail
    def test_overrides_outer_scope_values(
        self, root_provider, app_provider, op_provider
    ):
        root_provider.provides('value', str, lambda: 'root-scope-value')
        app_provider.provides('value', str, lambda: 'app-scope-value')
        op_provider.provides('value', str, lambda: 'op-scope-value')
        assert root_provider.provide('value', str) == 'root-scope-value'
        assert app_provider.provide('value', str) == 'app-scope-value'
        assert op_provider.provide('value', str) == 'op-scope-value'

    def test_provides_distinct_instances_for_same_scope_lvl(
        self, container, root_provider
    ):
        value_factory = Mock(name='value-factory', wraps=Foo)
        container.provides_at_scope(Scope.app, 'value', Foo, value_factory)

        with provider_scope(
            root_provider, Scope.app
        ) as app_provider_1, provider_scope(
            root_provider, Scope.app
        ) as app_provider_2:
            val1 = app_provider_1.provide('value', Foo)
            val2 = app_provider_2.provide('value', Foo)
            assert val1 is not val2

        assert value_factory.mock_calls == [call(), call()]

    def test_deliveries_sub_deps(self, container):
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

        class Scope(IntEnum):
            root = 0
            app = 1
            handler = 2

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

        cfg_factory = Mock(name='cfg-factory')

        db_factory = Mock(name='db-factory')
        cache_factory = Mock(name='cache-factory')

        transaction_factory = Mock(name='transaction-factory')
        foo_ctrl_factory = Mock(name='foo-ctrl-factory')
        bar_ctrl_factory = Mock(name='bar-ctrl-factory')

        container.provides('cfg', Cfg, cfg_factory)
        container.provides_at_scope(
            Scope.app, 'db', DB, db_factory, cfg=('cfg', Cfg)
        )
        container.provides_at_scope(
            Scope.app, 'cache', Cache, cache_factory, cfg=('cfg', Cfg)
        )
        container.provides_at_scope(
            Scope.handler,
            'transaction',
            Transaction,
            transaction_factory,
            db=('db', DB),
        )
        container.provides_at_scope(
            Scope.handler,
            'foo_ctrl',
            FooCtrl,
            foo_ctrl_factory,
            transaction=('transaction', Transaction),
        )
        container.provides_at_scope(
            Scope.handler,
            'bar_ctrl',
            BarCtrl,
            bar_ctrl_factory,
            transaction=('transaction', Transaction),
            cache=('cache', Cache),
        )

        with provider_scope(container) as root_provider:
            with provider_scope(root_provider, Scope.app) as app_provider:
                with provider_scope(
                    app_provider, Scope.handler
                ) as handler_provider:
                    foo_ctrl = handler_provider.provide('foo_ctrl', FooCtrl)
                    bar_ctrl = handler_provider.provide('bar_ctrl', BarCtrl)

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
