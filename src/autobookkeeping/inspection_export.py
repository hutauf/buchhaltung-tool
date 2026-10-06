"""Lossless CSV views and machine-readable field descriptions, outside the repos."""
from __future__ import annotations

import csv
import io

from autobookkeeping.archive import atomic, encoded, sha


def pointer(path):
    return "".join("/" + str(key).replace("~", "~0").replace("/", "~1") for key in path)


def nodes(value, path=()):
    if isinstance(value, dict):
        kind, text = "object", ""
    elif isinstance(value, list):
        kind, text = "array", ""
    elif value is None:
        kind, text = "null", ""
    elif isinstance(value, bool):
        kind, text = "boolean", "true" if value else "false"
    elif isinstance(value, (int, float)):
        kind, text = "number", encoded(value).decode().strip()
    else:
        kind, text = "string", value
    yield {"path": pointer(path), "parent": pointer(path[:-1]) if path else "",
           "key": str(path[-1]) if path else "", "type": kind, "value": text}
    if isinstance(value, (dict, list)):
        children = sorted(value.items()) if isinstance(value, dict) else enumerate(value)
        for key, child in children:
            yield from nodes(child, path + (key,))


def records(catalog):
    for section in ("records", "local_invoice_drafts", "local_adjustment_drafts", "local_expense_drafts"):
        for identifier, versions in catalog.get(section, {}).items():
            for version, row in [("current", versions["current"]), *[
                (f"history:{i}", old) for i, old in enumerate(versions["history"])
            ]]:
                path = (section, identifier, "current") if version == "current" else (
                    section, identifier, "history", int(version.split(":")[1]))
                result = {"section": section, "id": identifier, "version": version, "path": pointer(path)}
                for field in ("kind", "number", "date", "status", "currency", "gross", "net", "vat", "pay_date"):
                    value = row.get(field)
                    result[field] = "" if value is None else str(value)
                yield result, row


def write_tables(target, catalog, exported_documents):
    descriptions = {
        "catalog-nodes.csv": {
            "path": "Unique RFC6901 JSON pointer into catalog.json; root is empty",
            "parent": "Parent JSON pointer; relates to path in this table",
            "key": "Object key or zero-based array index; root is empty",
            "type": "object, array, null, boolean, number or string",
            "value": "Unmodified string, JSON number, true/false; empty for containers/null",
        },
        "records.csv": {
            "section": "records or local draft collection; drafts are not issued/booked records",
            "id": "Collection key; compound key with section and version",
            "version": "current or history:INDEX; INDEX is zero-based",
            "path": "Foreign key to catalog-nodes.csv path",
            "kind": "Document kind as recorded",
            "number": "Document number as TEXT, preserving leading zeroes",
            "date": "Recorded document date; empty means not recorded",
            "status": "Recorded source/workflow status",
            "currency": "Recorded currency; empty means not recorded",
            "gross": "Recorded gross amount; decimal point, currency units; empty is unknown",
            "net": "Recorded net amount; decimal point, currency units; empty is unknown",
            "vat": "Recorded tax amount; decimal point, currency units; empty is unknown",
            "pay_date": "Recorded payment date; empty does not prove a payment",
        },
        "documents.csv": {
            "reference": "Original encrypted document reference; unique key",
            "exported_path": "Relative plaintext path inside this export",
            "sha256_plaintext": "SHA256 of the original unencrypted bytes",
            "bytes_plaintext": "Original byte length; integer",
            "record_id": "Recorded owner ID; resolve through catalog.json and catalog-nodes.csv",
            "role": "Recorded document role; may be empty in historical entries",
        },
        "record-documents.csv": {
            "record_path": "Foreign key to records.csv path and catalog-nodes.csv path",
            "position": "Zero-based index in the record's documents array",
            "reference": "Foreign key to documents.csv reference",
        },
    }
    record_rows, links = [], []
    for row, source in records(catalog):
        record_rows.append(row)
        links.extend({"record_path": row["path"], "position": index, "reference": name}
                     for index, name in enumerate(source.get("documents", [])))
    document_rows = [dict(entry, reference=name) for name, entry in exported_documents.items()]
    tables = {"catalog-nodes.csv": nodes(catalog), "records.csv": record_rows,
              "documents.csv": document_rows, "record-documents.csv": links}
    hashes = {}
    for name, rows in tables.items():
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=list(descriptions[name]), extrasaction="ignore",
                                delimiter=";", quoting=csv.QUOTE_ALL, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        data = buffer.getvalue().encode("utf-8")
        atomic(target / name, data)
        hashes[name] = sha(data)
    description = {"version": 1, "scope": "complete", "encoding": "UTF-8", "delimiter": ";",
        "quote": '"', "quote_escape": '""', "line_ending": "LF", "catalog_sha256": sha(encoded(catalog)),
        "tables": {name: {"columns": {field: {"description": text,
            "type": "decimal" if field in ("gross", "net", "vat") else
                    "integer" if field in ("position", "bytes_plaintext") else "text",
            "empty_means": "missing_or_not_recorded" if field in ("gross", "net", "vat", "date", "pay_date", "currency", "role", "number", "kind", "status", "record_id") else "literal_empty_string",
            "decimal_separator": "." if field in ("gross", "net", "vat") else None}
            for field, text in fields.items()}, "sha256": hashes[name]} for name, fields in descriptions.items()},
        "notes": ["catalog-nodes.csv preserves every value, container and relationship, including histories and audit records.",
                  "records.csv is a convenience view; nested, mixed-tax and additional fields remain in catalog-nodes.csv.",
                  "No year filter removes data. No statutory national import profile or full tax return is asserted."]}
    atomic(target / "data-description.json", encoded(description))
    hashes["data-description.json"] = sha(encoded(description))
    return hashes
