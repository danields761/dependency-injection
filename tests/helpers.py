import abc
from typing import Protocol, runtime_checkable


class A:
    pass


class B:
    pass


class C:
    def __init__(self, a: A, b: B):
        self.a = a
        self.b = b


class DepOnA:
    def __init__(self, a: A):
        self.a = a


@runtime_checkable
class FooProto(Protocol):
    def bar(self):
        raise NotImplementedError


class FooABC(abc.ABC):
    @abc.abstractmethod
    def bar(self):
        raise NotImplementedError


class Foo:
    def bar(self):
        return 'unbound-foo'


class FooInheritor(Foo):
    pass


class NominalFooABC(FooABC):
    def bar(self):
        return 'nominal-abc-foo'


class NominalFooProto(FooProto):
    def bar(self):
        return 'nominal-proto-foo'


A_INST = A()
B_INST = B()
