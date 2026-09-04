"""Bounded tool discovery and local-only schema validation."""

from copy import deepcopy
import json

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

from app.contracts.mcp_evidence import digest_json

ALLOWED_TOOLS = frozenset({"map_search_places", "map_place_details"})


class MCPBoundaryError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _safe_schema(value, depth=0):
    if depth > 24:
        raise MCPBoundaryError("schema_depth_exceeded")
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"$ref", "$dynamicRef", "$recursiveRef"}:
                # These two provider tools need only flat primitive arguments.
                raise MCPBoundaryError("schema_reference_denied")
            _safe_schema(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _safe_schema(item, depth + 1)


class ToolCatalog:
    def __init__(self, tools: list[dict]):
        self._schemas = {}
        for tool in tools:
            name = tool["name"]
            if name not in ALLOWED_TOOLS:
                continue
            if name in self._schemas:
                raise MCPBoundaryError("duplicate_tool")
            schema = deepcopy(tool["inputSchema"])
            _safe_schema(schema)
            try:
                Draft202012Validator.check_schema(schema)
            except SchemaError:
                raise MCPBoundaryError("invalid_tool_schema") from None
            if schema.get("type") != "object":
                raise MCPBoundaryError("invalid_tool_schema")
            self._schemas[name] = schema
        if set(self._schemas) != ALLOWED_TOOLS:
            raise MCPBoundaryError("required_tool_missing")

    @property
    def names(self):
        return tuple(sorted(self._schemas))

    @property
    def hashes(self):
        return {name: digest_json(schema) for name, schema in self._schemas.items()}

    def schema(self, name):
        if name not in self._schemas:
            raise MCPBoundaryError("tool_not_allowed")
        return deepcopy(self._schemas[name])

    def validate(self, name, arguments):
        schema = self.schema(name)
        if not isinstance(arguments, dict) or len(json.dumps(arguments).encode()) > 16384:
            raise MCPBoundaryError("invalid_arguments")
        if set(arguments) - set(schema.get("properties", {})):
            raise MCPBoundaryError("invalid_arguments")
        try:
            Draft202012Validator(schema).validate(arguments)
        except (ValidationError, RecursionError):
            raise MCPBoundaryError("invalid_arguments") from None
