from typing import Type, Optional, Any


def _repr_type(type_):
    if isinstance(type_, type):
        return f'{type_.__module__}.{type_.__name__}'
    return repr(type_)


class DependencyLookupError(LookupError):
    def __init__(
        self,
        dep_name: str,
        required_type: Type,
        details: Optional[str] = None,
    ):
        super().__init__(dep_name, required_type, details)
        self.dep_name = dep_name
        self.required_type = required_type
        self.details = details

    def __str__(self) -> str:
        return f"""Dependency `{
            self.dep_name
        }: {
            _repr_type(self.required_type)
        }` lookup error{
            ''
            if not self.details
            else f': {self.details}'
        }"""


class DependencyTypeMismatchError(DependencyLookupError, TypeError):
    def __init__(
        self,
        dep_name: str,
        required_type: Type,
        provided_type: Type,
    ):
        super().__init__(
            dep_name,
            required_type,
            f'provided type is `{_repr_type(provided_type)}`',
        )
        self.provided_type = provided_type
