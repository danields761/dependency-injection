import abc
from typing import (
    AbstractSet,
    AsyncContextManager,
    AsyncGenerator,
    AsyncIterable,
    AsyncIterator,
    Awaitable,
    ByteString,
    ChainMap,
    Collection,
    Container,
    ContextManager,
    Coroutine,
    Counter,
    DefaultDict,
    Deque,
    Dict,
    FrozenSet,
    Generator,
    Hashable,
    ItemsView,
    Iterable,
    Iterator,
    KeysView,
    List,
    Mapping,
    MappingView,
    MutableMapping,
    MutableSequence,
    MutableSet,
    NamedTuple,
    OrderedDict,
    Protocol,
    Reversible,
    Sequence,
    Set,
    Sized,
    SupportsAbs,
    SupportsBytes,
    SupportsComplex,
    SupportsFloat,
    SupportsIndex,
    SupportsInt,
    SupportsRound,
    Type,
    TypedDict,
    ValuesView,
    get_origin,
)

_ALL_STD_ALIASES = [
    Protocol,
    AbstractSet,
    ByteString,
    Container,
    ContextManager,
    Hashable,
    ItemsView,
    Iterable,
    Iterator,
    KeysView,
    Mapping,
    MappingView,
    MutableMapping,
    MutableSequence,
    MutableSet,
    Sequence,
    Sized,
    ValuesView,
    Awaitable,
    AsyncIterator,
    AsyncIterable,
    Coroutine,
    Collection,
    AsyncGenerator,
    AsyncContextManager,
    Reversible,
    SupportsAbs,
    SupportsBytes,
    SupportsComplex,
    SupportsFloat,
    SupportsIndex,
    SupportsInt,
    SupportsRound,
    ChainMap,
    Counter,
    Deque,
    Dict,
    DefaultDict,
    List,
    OrderedDict,
    Set,
    FrozenSet,
    NamedTuple,
    TypedDict,
    Generator,
]


def is_user_st_protocol(t: Type) -> bool:
    t_orig = get_origin(t) or t
    if t_orig in _ALL_STD_ALIASES:
        return False
    return issubclass(t_orig, Protocol) and not is_abc(t)


def is_user_st_runtime_protocol(t: Type) -> bool:
    t_orig = get_origin(t) or t
    if not is_user_st_protocol(t):
        return False
    return getattr(t_orig, '_is_runtime_protocol', False)


def is_abc(t: Type) -> bool:
    t_orig = get_origin(t) or t
    return issubclass(type(t_orig), abc.ABCMeta) and (
        not hasattr(t_orig, '_is_protocol') or not getattr(t_orig, '_is_protocol')
    )


class TypesMatcher(Protocol):
    def __call__(self, target_acceptable: Type, in_place_of: Type) -> bool:
        """
        reminder: Sequence = list()
                  ^          ^
            in_place_of  target_acceptable
          issubclass(list, Sequence)
          issubclass(acceptable, in_place_of)
          issubclass(dep.provides, look_type)

        :param target_acceptable:
        :param in_place_of:
        :return:
        """
        raise NotImplementedError


def is_type_acceptable_in_place_of(type_acceptable: Type, in_place_of: Type) -> bool:
    # Vandally strip subscribed generics to their origins, anyway precise type
    # checking is not supported right now
    type_acceptable = get_origin(type_acceptable) or type_acceptable
    in_place_of = get_origin(in_place_of) or in_place_of

    # TODO raise if pair unmatchable

    return issubclass(type_acceptable, in_place_of)


def _ensure_types_checkable(type_acceptable: Type, in_place_of: Type) -> None:
    # If `t2` is not parent of `t1`, so in case when right side is not
    # runtime-checkable Protocol, throw according error
    if in_place_of not in type_acceptable.__bases__:
        if (
            not is_abc(in_place_of)
            and is_user_st_protocol(in_place_of)
            and not is_user_st_runtime_protocol(in_place_of)
        ):
            raise TypeError(
                f'Checking against non-runtime Protocol "{in_place_of}" '
                'is not supported, consider use the '
                '`typing.runtime_protocol` decorator,'
                'or inherit classes explicitly'
            )
