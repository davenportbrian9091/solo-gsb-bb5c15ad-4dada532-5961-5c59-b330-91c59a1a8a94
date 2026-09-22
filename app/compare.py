"""Validation result comparison.

Computes the delta between two finished validations:

* diagnostics are compared by a stable fingerprint made of
  ``(type, severity, path, line, message, details)``;
* documents of the two imports are classified as added, removed or
  content-changed by path.

"Added" diagnostics appear in the target validation but not in the base one;
"removed" diagnostics exist in the base but not in the target. Diagnostics
that share a fingerprint in both validations are "unchanged".
"""
from __future__ import annotations

import json
from collections import Counter

# Fields that define the stable diagnostic fingerprint, in order.
FINGERPRINT_FIELDS = ("type", "severity", "path", "line", "message", "details")


def diagnostic_fingerprint(diag: dict) -> str:
    """Stable identity of a diagnostic.

    The ``details`` object is compared structurally, so key insertion order
    (or differences between stored and re-parsed JSON) does not matter.
    """
    return json.dumps(
        [diag[field] for field in FINGERPRINT_FIELDS],
        ensure_ascii=False,
        sort_keys=True,
    )


def public_diagnostic(diag: dict) -> dict:
    """Serialize a stored diagnostic row with the six public fields."""
    return {field: diag[field] for field in FINGERPRINT_FIELDS}


def _sort_key(diag: dict) -> tuple:
    # Doc-level diagnostics (line is NULL, e.g. cycles) sort first, matching
    # the analyzer and SARIF export ordering.
    return (
        diag["path"],
        diag["line"] if diag["line"] is not None else -1,
        diag["type"],
        diag["message"],
    )


def diff_diagnostics(
    base_diagnostics: list[dict], target_diagnostics: list[dict]
) -> dict[str, list[dict]]:
    """Multiset diff of diagnostics keyed by their stable fingerprint."""
    base_by_fp: Counter[str] = Counter(
        diagnostic_fingerprint(d) for d in base_diagnostics
    )
    target_by_fp: Counter[str] = Counter(
        diagnostic_fingerprint(d) for d in target_diagnostics
    )

    added: list[dict] = []
    removed: list[dict] = []
    unchanged: list[dict] = []

    for diag in target_diagnostics:
        fp = diagnostic_fingerprint(diag)
        if base_by_fp.get(fp, 0) > 0:
            base_by_fp[fp] -= 1
            unchanged.append(public_diagnostic(diag))
        else:
            added.append(public_diagnostic(diag))

    for diag in base_diagnostics:
        fp = diagnostic_fingerprint(diag)
        if target_by_fp.get(fp, 0) > 0:
            target_by_fp[fp] -= 1
        else:
            removed.append(public_diagnostic(diag))
    for bucket in (added, removed, unchanged):
        bucket.sort(key=_sort_key)
    return {"added": added, "removed": removed, "unchanged": unchanged}


def diff_documents(
    base_documents: dict[str, str], target_documents: dict[str, str]
) -> dict[str, list[str]]:
    """Classify import paths as added, removed or content-changed."""
    base_paths = set(base_documents)
    target_paths = set(target_documents)
    return {
        "added": sorted(target_paths - base_paths),
        "removed": sorted(base_paths - target_paths),
        "changed": sorted(
            path
            for path in base_paths & target_paths
            if base_documents[path] != target_documents[path]
        ),
    }


def build_comparison(
    base_validation: dict,
    target_validation: dict,
    base_diagnostics: list[dict],
    target_diagnostics: list[dict],
    base_documents: dict[str, str],
    target_documents: dict[str, str],
) -> dict:
    """Assemble the full compare response for two finished validations."""
    diagnostic_diff = diff_diagnostics(base_diagnostics, target_diagnostics)
    document_diff = diff_documents(base_documents, target_documents)
    return {
        "base_validation_id": base_validation["id"],
        "target_validation_id": target_validation["id"],
        "base_import_id": base_validation["import_id"],
        "target_import_id": target_validation["import_id"],
        "diagnostics": {
            **diagnostic_diff,
            "counts": {
                "added": len(diagnostic_diff["added"]),
                "removed": len(diagnostic_diff["removed"]),
                "unchanged": len(diagnostic_diff["unchanged"]),
            },
        },
        "documents": document_diff,
    }
