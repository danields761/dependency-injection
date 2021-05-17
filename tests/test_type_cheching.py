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
    is_type_acceptable_in_place_of,
    is_user_st_protocol,
    is_user_st_runtime_protocol,
)
from tests.helpers import Foo, FooABC, FooInheritor, FooProto, NominalFooABC

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
@mark.xfail
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


@mark.parametrize(
    'type_acceptable, in_place_of, is_match',
    [
        (list, list[int], True),
        (list[int], Sequence, True),
        (Foo, FooProto, True),
        (FooABC, FooProto, True),
        (FooInheritor, Foo, True),
        (FooInheritor, FooProto, True),
        (NominalFooABC, FooABC, True),
        # `abc.ABC` doesn't support structural typing, and we do so
        # (maybe will be altered in future)
        (
            Foo,
            FooABC,
            False,
        ),
        (
            FooProto,
            FooABC,
            False,
        ),
    ],
)
def test_types_consistency(type_acceptable, in_place_of, is_match):
    assert (
        is_type_acceptable_in_place_of(type_acceptable, in_place_of)
        is is_match
    )
