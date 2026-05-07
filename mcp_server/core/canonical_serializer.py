"""Convert canonical dataclasses to JSON-serializable dicts.

MCP tools return JSON over the wire. Alfred's frozen dataclasses
(:class:`Event`, :class:`Message`, :class:`Ticket`, :class:`SearchHit`,
:class:`Person`) carry :class:`datetime` fields and :class:`MappingProxyType`
``raw`` escape hatches that :func:`json.dumps` cannot serialize on its
own. This module owns the projection.

Mapping rules:

- :class:`datetime` → ISO 8601 string. Aware datetimes include the
  offset (``"…+00:00"``); naive datetimes (all-day calendar events) emit
  without one.
- frozen dataclass → ``{field_name: converted_value}`` dict.
- :class:`Mapping` (incl. :class:`MappingProxyType`) → plain ``dict``.
- ``tuple`` / ``list`` → ``list`` of converted items.
- ``None``, ``str``, ``int``, ``float``, ``bool`` pass through.

Pure functions; no I/O.
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import datetime
from typing import Any, Mapping

from mcp_server.core.canonical import SearchHit, SourceItem


def to_jsonable(item: SourceItem | SearchHit) -> dict[str, Any]:
    """Convert a canonical item to a JSON-serializable ``dict``."""
    result = _convert(item)
    if not isinstance(result, dict):
        raise TypeError(
            f"to_jsonable expected a dataclass; got {type(item).__name__}"
        )
    return result


def _convert(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)):
        return value
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: _convert(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, Mapping):
        return {k: _convert(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_convert(v) for v in value]
    raise TypeError(
        f"unsupported type for serialization: {type(value).__name__}"
    )
