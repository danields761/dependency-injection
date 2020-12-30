from typing import List, Union, Iterable, Sequence, Dict
from unittest.mock import Mock

from pytest import raises, fixture, mark

from dependency_injection.container import MutableContainer, container_scope, \
    ROOT_SCOPE
from dependency_injection.models import Scope
from dependency_injection.provider import Provider


class Foo:
    pass


class Bar:
    def __init__(self, foo: Foo):
        self.foo = foo


class BarImpl(Bar):
    def __init__(self, foo: Foo, param: int):
        super().__init__(foo)
        self.param = param


APP_SCOPE = Scope('APP_SCOPE', ROOT_SCOPE)
OP_SCOPE = Scope('CUSTOM_SCOPE', APP_SCOPE)


@fixture
def root_ctr():
    return MutableContainer()


@fixture
def app_ctr(root_ctr):
    with container_scope(root_ctr, APP_SCOPE) as app_ctr_:
        yield app_ctr_


@fixture
def op_ctr(app_ctr):
    with container_scope(app_ctr, OP_SCOPE) as op_ctr_:
        yield op_ctr_


def test_container_root_scope_is_default(root_ctr):
    assert root_ctr.current_scope == ROOT_SCOPE


def test_container_cant_provide_values_in_root_scope(root_ctr):
    root_ctr.provides('foo', Foo)

    with raises(RuntimeError) as exc_info:
        root_ctr.lookup_resolver('foo', Foo)
    assert str(exc_info.value) == 'Could not provide while in root scope'


def test_container_cant_enter_indirect_scope(root_ctr):
    with raises(RuntimeError) as exc_info:
        container_scope(root_ctr, OP_SCOPE).__enter__()
    assert str(exc_info.value) == 'Could not enter indirect scope'


def test_container_provides_simple_value(root_ctr):
    root_ctr.provides('value', int, lambda: 100)
    with container_scope(root_ctr, APP_SCOPE) as app_ctr:
        assert app_ctr.resolve('value', int) == 100


def test_container_cant_register_provider_for_ambiguous_types(root_ctr):
    with raises(RuntimeError) as exc_info:
        root_ctr.provides('value', lambda: 100)
    assert (
        str(exc_info.value) == 'Could not register provider for ambiguous type'
    )


def test_container_provides_class_instance_registered_without_factory(
    root_ctr, app_ctr
):
    root_ctr.provides('foo', Foo)
    foo = app_ctr.resolve('foo', Foo)
    assert isinstance(foo, Foo)


@mark.parametrize(
    'provides_type, requested_type, expects_value',
    [
        (BarImpl, Bar, BarImpl(Foo(), 100)),
        (List[int], Iterable[int], [1, 2, 3]),
        (List[int], Sequence[int], [1, 2, 3]),
        (int, Union[str, int], 100),
        (str, Union[str, int], 'test-string'),
        (List[int], List[Union[str, int]], [1, 2, 3]),
        (List[str], List[Union[str, int]], ['v1', 'v2', 'v3']),
        (List[int], Iterable[Union[str, int]], [1, 2, 3]),
        (List[str], Iterable[Union[str, int]], ['v1', 'v2', 'v3']),
        (Dict[str, int], Iterable[Union[str, int]], {'k1': 1, 'k2': 2}),
        (Dict[str, str], Iterable[Union[str, int]], ['v1', 'v2', 'v3']),
        # TODO Protocol should be tested as well
    ],
)
def test_dependencies_could_be_resolved_requesting_supertypes(
    root_ctr,
    app_ctr,
    provides_type,
    requested_type,
    expects_value,
):
    root_ctr.provides('test_name', provides_type, lambda: expects_value)
    value = app_ctr.resolve('test_name', requested_type)
    assert value == expects_value


@mark.parametrize(
    'provides_type, requested_type',
    [
        (Iterable[int], List[int]),
        (List[Union[str, int]], List[int]),
        (List[Union[str, int]], Iterable[int]),
        (Bar, BarImpl),
    ],
)
def test_cant_specialize_type_on_provide(
    root_ctr, app_ctr, provides_type, requested_type
):
    root_ctr.provides('value', provides_type, lambda: 100)
    with raises(LookupError) as exc_info:
        app_ctr.resolve('value', requested_type)
    assert str(exc_info.value) == (
        'Could not provide value requested via '
        'narrower type that it is provided'
    )


def test_provides_at_scope(root_ctr, app_ctr):
    root_ctr.provides('foo', Foo)
    root_ctr.provides_at_scope(OP_SCOPE, 'bar', Bar, foo=('foo', Foo))

    with raises(LookupError) as exc_info:
        app_ctr.lookup_resolver('bar', Bar)
    assert str(exc_info.value) == (
        'Could not find provider for "bar" of type "Bar", '
        'but it was declared for future scope "OP_SCOPE"'
    )

    with container_scope(app_ctr, OP_SCOPE) as op_ctr:
        bar = op_ctr.resolve('bar', Bar)
        assert isinstance(bar, Bar)
        assert bar.foo is op_ctr.resolve('foo', Foo)


def test_provides_at_scope_cant_provide_for_outer_scope(app_ctr):
    with container_scope(app_ctr, OP_SCOPE) as op_ctr:
        with raises(RuntimeError) as exc_info:
            op_ctr.provides_at_scope(APP_SCOPE, 'test', Foo)
        assert str(exc_info.value) == 'Could not provide for outer scope'


def test_provides_at_scope_forbids_resolving_outside(app_ctr, op_ctr):
    pass


def test_inherits_values_from_outer_scope(root_ctr):
    foo_mock = Mock(name='foo')
    root_ctr.provides('foo', Foo, lambda: foo_mock)
    with container_scope(root_ctr, APP_SCOPE) as app_ctr:
        with container_scope(app_ctr, OP_SCOPE) as op_ctr:
            assert op_ctr.resolve('foo', Foo) is foo_mock
        assert app_ctr.resolve('foo', Foo) is foo_mock


def test_overrides_outer_scope_values(root_ctr, app_ctr, op_ctr):
    root_ctr.provides('value', str, lambda: 'root-scope-value')
    app_ctr.provides('value', str, lambda: 'app-scope-value')
    op_ctr.provides('value', str, lambda: 'op-scope-value')
    assert root_ctr.resolve('value', str) == 'root-scope-value'
    assert app_ctr.resolve('value', str) == 'app-scope-value'
    assert op_ctr.resolve('value', str) == 'op-scope-value'


def test_scope_containers_independent_but_inherits_common_container(root_ctr):
    root_ctr.provides('value', str, lambda: 'root-scope-value')
    with container_scope(root_ctr, APP_SCOPE) as app_ctr1, container_scope(
        root_ctr, APP_SCOPE
    ) as app_ctr2:
        assert app_ctr1 is not app_ctr2
        assert (
            app_ctr1.resolve('value', str)
            == app_ctr2.resolve('value', str)
            == 'root-scope-value'
        )
        # TODO Should it really be mutable? Which kind of surprising
        #  side-effects it might have?
        app_ctr1.provides('value', str, lambda: 'app-scope-1-value')
        app_ctr2.provides('value', str, lambda: 'app-scope-2-value')

        assert app_ctr1.resolve('value', str) == 'app-scope-1-value'
        assert app_ctr2.resolve('value', str) == 'app-scope-2-value'


def test_container():
    root_ctr = MutableContainer()
    root_ctr.provides('foo', Foo)
    root_ctr.provides('bar', Bar, foo=('foo', Foo))
    root_ctr.provides('param', lambda: 100)

    with container_scope(root_ctr, APP_SCOPE) as app_ctr:
        foo_provider = app_ctr.lookup_resolver('foo', Foo)
        assert isinstance(foo_provider, Provider)
        foo = foo_provider.provide()
        assert isinstance(foo, Foo)

        bar_provider = app_ctr.lookup_resolver('bar', Bar)
        assert isinstance(bar_provider, Provider)
        bar = bar_provider.provide()
        assert isinstance(bar, Bar) and not isinstance(bar, BarImpl)
        assert bar.foo is foo

        with container_scope(app_ctr, OP_SCOPE) as op_ctr:
            op_ctr.provides(
                'bar', Bar, BarImpl, foo=('foo', Foo), param=('param', int)
            )

            bar_provider2 = op_ctr.lookup_resolver('bar', Bar)
            assert isinstance(bar_provider2, Provider)
            bar2 = bar_provider2.provide()
            assert isinstance(bar2, BarImpl)
            assert bar2.foo is foo
            assert bar2.param == 100
