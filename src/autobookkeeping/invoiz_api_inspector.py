from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


INTERESTING_PATH_PARTS = (
    "invoice",
    "expense",
    "customer",
    "setting/payCondition",
    "auth/token",
)
INTERESTING_SCHEMAS = (
    "PostInvoice",
    "Invoice",
    "InvoicePosition",
    "InvoicePayment",
    "Expense",
    "ExpenseReceipt",
    "Customer",
    "CustomerData",
    "PayCondition",
)


def inspect_invoiz_api(path: Path) -> dict[str, Any]:
    doc = load_openapi_like(path)
    return {
        "source": str(path),
        "title": _get(doc, "info", "title") or doc.get("title"),
        "version": _get(doc, "info", "version") or doc.get("version"),
        "servers": doc.get("servers", []),
        "paths": _summarize_paths(doc.get("paths", {})),
        "schemas": _summarize_schemas(_get(doc, "components", "schemas") or {}),
    }


def load_openapi_like(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    candidates = [text]

    swagger_doc = _extract_js_object(text, '"swaggerDoc"')
    if swagger_doc:
        candidates.insert(0, swagger_doc)

    first_object = _extract_first_object(text)
    if first_object and first_object not in candidates:
        candidates.append(first_object)

    for candidate in candidates:
        for normalized in _normalization_variants(candidate):
            try:
                value = json.loads(normalized)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                return _normalize_doc(value)

    raise ValueError(f"Could not parse {path} as JSON/OpenAPI/Swagger JS fragment")


def _summarize_paths(paths: dict[str, Any]) -> dict[str, Any]:
    result = {}
    for path, path_spec in sorted(paths.items()):
        if not any(part.lower() in path.lower() for part in INTERESTING_PATH_PARTS):
            continue
        methods = {}
        for method, operation in sorted(path_spec.items()):
            if not isinstance(operation, dict):
                continue
            methods[method.upper()] = {
                "summary": operation.get("summary"),
                "operationId": operation.get("operationId"),
                "parameters": [
                    {
                        "name": param.get("name"),
                        "in": param.get("in"),
                        "required": bool(param.get("required")),
                    }
                    for param in operation.get("parameters", [])
                    if isinstance(param, dict)
                ],
                "requestBody": _request_body_summary(operation.get("requestBody")),
            }
        result[path] = methods
    return result


def _summarize_schemas(schemas: dict[str, Any]) -> dict[str, Any]:
    result = {}
    for name in INTERESTING_SCHEMAS:
        schema = schemas.get(name)
        if not isinstance(schema, dict):
            continue
        properties = schema.get("properties") or {}
        result[name] = {
            "required": schema.get("required", []),
            "properties": sorted(properties.keys()) if isinstance(properties, dict) else [],
        }
    return result


def _request_body_summary(request_body: Any) -> dict[str, Any] | None:
    if not isinstance(request_body, dict):
        return None
    content = request_body.get("content") or {}
    result: dict[str, Any] = {"contentTypes": sorted(content.keys())}
    json_content = content.get("application/json")
    if isinstance(json_content, dict):
        result["jsonSchema"] = json_content.get("schema")
        examples = json_content.get("examples")
        if isinstance(examples, dict):
            result["exampleNames"] = sorted(examples.keys())
    multipart = content.get("multipart/form-data")
    if isinstance(multipart, dict):
        result["multipartSchema"] = multipart.get("schema")
    return result


def _normalize_doc(value: dict[str, Any]) -> dict[str, Any]:
    if "paths" in value:
        return value
    if "swaggerDoc" in value and isinstance(value["swaggerDoc"], dict):
        return value["swaggerDoc"]
    raise ValueError("Parsed JSON does not look like OpenAPI")


def _normalization_variants(text: str) -> list[str]:
    stripped = text.strip()
    variants = [stripped]
    if stripped.startswith("{") and '"title"' in stripped[:500] and '"paths"' in stripped:
        variants.append('{"openapi":"3.0.2","info":' + stripped)
    no_trailing_commas = re.sub(r",\s*([}\]])", r"\1", stripped)
    if no_trailing_commas != stripped:
        variants.append(no_trailing_commas)
        if no_trailing_commas.startswith("{") and '"title"' in no_trailing_commas[:500]:
            variants.append('{"openapi":"3.0.2","info":' + no_trailing_commas)
    return variants


def _extract_js_object(text: str, key: str) -> str | None:
    key_pos = text.find(key)
    if key_pos == -1:
        return None
    colon = text.find(":", key_pos + len(key))
    if colon == -1:
        return None
    brace = text.find("{", colon)
    if brace == -1:
        return None
    return _balanced_object(text, brace)


def _extract_first_object(text: str) -> str | None:
    brace = text.find("{")
    if brace == -1:
        return None
    return _balanced_object(text, brace)


def _balanced_object(text: str, start: int) -> str | None:
    depth = 0
    in_string = False
    escape = False
    for idx in range(start, len(text)):
        char = text[idx]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : idx + 1]
    return None


def _get(value: dict[str, Any], *keys: str) -> Any:
    current: Any = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current
