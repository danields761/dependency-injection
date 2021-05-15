import abc
from typing import (
    Dict,
    Generic,
    Mapping,
    Protocol,
    Sequence,
    TypeVar,
    runtime_checkable,
)

from pytest import mark

from dependency_injection.types_match import (
    is_abc,
    is_user_st_protocol,
    is_user_st_runtime_protocol,
)

T = TypeVar('T')


class Proto(Protocol):
    pass


class GenericProto(Protocol[T]):
    pass


@runtime_checkable
class RuntimeProto(Protocol):
    pass


@runtime_checkable
class GenericRuntimeProto(Protocol[T]):
    pass


class ABCClass(abc.ABC):
    pass


class GenericABCClass(abc.ABC, Generic[T]):
    pass


@mark.parametrize(
    'maybe_abc, excepted_result',
    [
        (Protocol, False),
        (Protocol[T], False),
        (Proto, False),
        (GenericProto[int], False),
        (RuntimeProto, False),
        (GenericRuntimeProto[int], False),
        (ABCClass, True),
        (GenericABCClass[int], True),
    ],
)
def test_is_abc(maybe_abc, excepted_result):
    assert is_abc(maybe_abc) is excepted_result


@mark.parametrize(
    'maybe_proto, excepted_result',
    [
        (Protocol, False),
        (Proto, True),
        (GenericProto[int], True),
        (RuntimeProto, True),
        (GenericRuntimeProto[int], True),
        (ABCClass, False),
        (GenericABCClass[int], False),
    ]
    +
    # All generic standard library aliases should not be recognized as
    # user-defined protocols
    # There is some of them
    [
        (std_alias, False)
        for std_alias in [
            Sequence,
            Dict,
            Mapping,
            Sequence[int],
            Dict[str, str],
        ]
    ],
)
@mark.xfail(todo=True)
def test_is_user_st_protocol(maybe_proto, excepted_result):
    assert is_user_st_protocol(maybe_proto) is excepted_result


@mark.parametrize(
    'maybe_abc, excepted_result',
    [
        (Protocol, False),
        (Protocol[T], False),
        (Proto, False),
        (GenericProto[int], False),
        (RuntimeProto, True),
        (GenericRuntimeProto[int], True),
        (ABCClass, False),
        (GenericABCClass[int], False),
    ],
)
def test_is_user_st_runtime_protocol(maybe_abc, excepted_result):
    assert is_user_st_runtime_protocol(maybe_abc) is excepted_result
