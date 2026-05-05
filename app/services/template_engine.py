from __future__ import annotations

from typing import Any

import structlog
from jinja2 import StrictUndefined
from jinja2.sandbox import SandboxedEnvironment

logger = structlog.get_logger(__name__)

WHITELISTED_FIELDS: frozenset[str] = frozenset(
    {"src", "text", "color", "background", "font_family", "callback"}
)

VARIABLE_TYPES: frozenset[str] = frozenset({"string", "url", "number", "boolean"})


class TemplateExpansionError(Exception):
    """Raised when Jinja2 template expansion fails."""

    def __init__(self, message: str, details: list[str] | None = None) -> None:
        self.details = details or []
        super().__init__(message)


class TemplateVariableError(Exception):
    """Raised when merge data fails variable schema validation."""

    def __init__(self, message: str, errors: list[str] | None = None) -> None:
        self.errors = errors or []
        super().__init__(message)


def validate_variable_schema(
    schema: dict[str, Any] | None,
    merge: dict[str, Any],
) -> dict[str, Any]:
    """Validate merge data against a template's variable_schema.

    Applies defaults for missing optional variables.
    Returns the validated and coerced merge dict.
    Raises TemplateVariableError on validation failures.
    """
    if not schema:
        return dict(merge)

    errors: list[str] = []
    result: dict[str, Any] = {}

    for var_name, var_def in schema.items():
        if not isinstance(var_def, dict):
            errors.append(f"Invalid schema definition for '{var_name}'")
            continue

        var_type = var_def.get("type", "string")
        required = var_def.get("required", False)
        default = var_def.get("default")

        if var_name in merge:
            value = merge[var_name]
            coerced = _coerce_value(var_name, value, var_type)
            if coerced is _COERCE_FAILED:
                errors.append(
                    f"Variable '{var_name}': expected type '{var_type}', "
                    f"got {type(value).__name__}"
                )
            else:
                result[var_name] = coerced
        elif required:
            errors.append(f"Missing required variable: '{var_name}'")
        elif default is not None:
            result[var_name] = default

    for key in merge:
        if key not in schema:
            result[key] = merge[key]

    if errors:
        raise TemplateVariableError(
            f"Variable validation failed: {len(errors)} error(s)",
            errors=errors,
        )

    return result


_COERCE_FAILED = object()


def _coerce_value(name: str, value: Any, var_type: str) -> Any:
    """Coerce a merge value to the expected schema type.

    Returns _COERCE_FAILED sentinel on type mismatch.
    """
    if var_type in ("string", "url"):
        if isinstance(value, str):
            return value
        if isinstance(value, (int, float, bool)):
            return str(value)
        return _COERCE_FAILED

    if var_type == "number":
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value
        if isinstance(value, str):
            try:
                return float(value) if "." in value else int(value)
            except ValueError:
                return _COERCE_FAILED
        return _COERCE_FAILED

    if var_type == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            if value.lower() in ("true", "1", "yes"):
                return True
            if value.lower() in ("false", "0", "no"):
                return False
            return _COERCE_FAILED
        return _COERCE_FAILED

    return value


_jinja_env = SandboxedEnvironment(undefined=StrictUndefined)


def expand_template(
    composition_dict: dict[str, Any],
    variables: dict[str, Any],
) -> dict[str, Any]:
    """Expand Jinja2 variables in whitelisted string fields only.

    Walks the composition dict recursively. Only string values whose
    dict key is in WHITELISTED_FIELDS are expanded through Jinja2.
    All other values pass through unchanged.

    Raises TemplateExpansionError if expansion fails.
    """
    try:
        result = _walk_and_expand(composition_dict, variables)
    except TemplateExpansionError:
        raise
    except Exception as exc:
        raise TemplateExpansionError(
            f"Template expansion failed: {exc}",
            details=[str(exc)],
        ) from exc

    logger.info(
        "template_expanded",
        variable_count=len(variables),
    )
    return result


def _walk_and_expand(
    node: Any,
    variables: dict[str, Any],
    parent_key: str | None = None,
) -> Any:
    """Recursively walk a dict/list structure, expanding whitelisted string fields."""
    if isinstance(node, dict):
        return {
            k: _walk_and_expand(v, variables, parent_key=k) for k, v in node.items()
        }
    if isinstance(node, list):
        return [
            _walk_and_expand(item, variables, parent_key=parent_key) for item in node
        ]
    if isinstance(node, str) and parent_key in WHITELISTED_FIELDS:
        return _expand_string(node, variables)
    return node


def _expand_string(template_str: str, variables: dict[str, Any]) -> str:
    """Expand a single string value through Jinja2 SandboxedEnvironment."""
    if "{{" not in template_str and "{%" not in template_str:
        return template_str
    try:
        tmpl = _jinja_env.from_string(template_str)
        return tmpl.render(variables)
    except Exception as exc:
        raise TemplateExpansionError(
            f"Failed to expand template string: {template_str!r}",
            details=[str(exc)],
        ) from exc
