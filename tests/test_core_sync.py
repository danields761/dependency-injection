from contextlib import AbstractContextManager, contextmanager
from typing import Callable
from unittest.mock import MagicMock, Mock, call

from pytest import raises

from dependency_injection.core import (
    Dependency,
    ImmutableContainer,
    create_resolver,
)
from tests.helpers import A_INST, B_INST, A, B, C


def test_calls_container_types_matcher():
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


def test_provides_simple():
    a_factory = Mock(Callable, name='a-factory', return_value=A_INST)
    container = ImmutableContainer(
        {'a': Dependency('a', A, requires={}, factory=a_factory)}
    )

    with create_resolver(container) as resolver:
        assert resolver.resolve('a', A) is A_INST
    assert a_factory.mock_calls == [call()]


def test_created_value_been_memoized_v1():
    container = ImmutableContainer({'a': Dependency('a', A, {}, factory=A)})
    with create_resolver(container) as resolver:
        a1 = resolver.resolve('a', A)
        a2 = resolver.resolve('a', A)
        assert a1 is a2


def test_created_value_been_memoized_v2():
    a_factory = Mock(Callable, name='a-factory')
    container = ImmutableContainer(
        {'a': Dependency('a', A, {}, factory=a_factory)}
    )
    with create_resolver(container) as resolver:
        a1 = resolver.resolve('a', A)
        a2 = resolver.resolve('a', A)
        assert a_factory.mock_calls == [call()]
        assert a1 is a2 is a_factory.return_value


def test_provides_with_deps():
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


def test_provides_dep_by_custom_arg_name():
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
        assert c_factory_mock.mock_calls == [call(a_arg=A_INST, b_arg=B_INST)]


def test_context_manager_factory():
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


def test_context_manager_as_sub_dep():
    @contextmanager
    def a_cm():
        yield A_INST

    container = ImmutableContainer(
        {
            'a': Dependency('a', A, {}, factory=a_cm, context_manager=True),
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


def test_there_is_recursion_error_TODO():
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
