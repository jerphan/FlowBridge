"""Typed in-memory contracts; no source parsing or execution."""
from __future__ import annotations

import json
import types
from dataclasses import dataclass, fields
from typing import Literal, Union, get_args, get_origin, get_type_hints

AnalysisStatus = Literal['success', 'partial', 'failed']
GraphStatus = Literal['complete', 'unsupported', 'failed']
ViewType = Literal['project', 'file', 'function', 'module']
NodeType = Literal['file', 'function', 'start', 'end', 'statement', 'condition',
                   'loop', 'return', 'break', 'continue', 'exceptionDispatch', 'handler', 'raise']
EdgeType = Literal['next', 'true', 'false', 'back', 'break', 'continue', 'return', 'exception', 'unhandled']


def _matches(value: object, annotation: object) -> bool:
    """Check only the types used by our contracts, without coercion."""
    origin = get_origin(annotation)
    arguments = get_args(annotation)
    if origin in (Union, types.UnionType):
        return any(_matches(value, option) for option in arguments)
    if origin is Literal:
        return any(type(value) is type(option) and value == option for option in arguments)
    if origin is list:
        return isinstance(value, list) and all(_matches(item, arguments[0]) for item in value)
    if origin is dict:
        return isinstance(value, dict) and all(
            _matches(key, arguments[0]) and _matches(item, arguments[1])
            for key, item in value.items())
    if annotation in (str, int, bool, type(None)):
        # bool subclasses int, but True is not a valid revision or coordinate.
        return type(value) is annotation
    if not isinstance(value, annotation):
        return False
    if isinstance(value, JsonModel):
        # Records are mutable. Recheck child fields before a parent accepts them,
        # so an edited edge or location cannot bypass its original validation.
        value.__post_init__()
    return True


def _camel_case(name: str) -> str:
    first, *remaining = name.split('_')
    return first + ''.join(part.title() for part in remaining)


def _encode(value: object) -> object:
    if isinstance(value, JsonModel):
        return value.to_dict()
    if isinstance(value, list):
        return [_encode(item) for item in value]
    if isinstance(value, dict):
        return {key: _encode(item) for key, item in value.items()}
    if value is None or type(value) in (str, int, bool):
        return value
    raise ValueError(f'Cannot serialize non-contract value: {type(value).__name__}')


def _unique(values: list[str], description: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f'Duplicate {description}')


@dataclass(kw_only=True)
class JsonModel:
    """Validate typed fields and serialize Python names as camelCase JSON keys."""

    def __post_init__(self) -> None:
        hints = get_type_hints(type(self))
        for item in fields(self):
            value = getattr(self, item.name)
            if not _matches(value, hints[item.name]):
                raise ValueError(f'{type(self).__name__}.{item.name}: invalid type or value')
            if isinstance(value, str) and (
                item.name.endswith('_id') or item.name in {'file_name', 'file_path', 'project_name'}
            ) and not value.strip():
                raise ValueError(f'{item.name} must not be blank')

    def to_dict(self) -> dict[str, object]:
        """Return fresh JSON containers, revalidating potentially mutated fields."""
        self.__post_init__()
        result: dict[str, object] = {}
        for item in fields(self):
            json_name = _camel_case(item.name)
            result[json_name] = _encode(getattr(self, item.name))
        return result

    def to_json(self) -> str:
        """Serialize deterministically while retaining source/list order."""
        return json.dumps(self.to_dict(), ensure_ascii=True, sort_keys=True, allow_nan=False)


