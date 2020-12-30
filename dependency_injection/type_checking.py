from typing import Type


def is_required_supertype_of_provided(provided: Type, required: Type) -> bool:
    if isinstance(provided, type) and isinstance(required, type):
        return issubclass(required, provided)
    raise NotImplementedError('Type concepts is not supported yet')
