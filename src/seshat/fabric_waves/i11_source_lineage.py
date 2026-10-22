"""Qualify original PDF bytes, model-fed page text, and later derived views.

A newly extracted F07/F08 UTF-8 view is never silently treated as the bytes
that were actually transferred to a terminal model job.
"""

from __future__ import annotations

import re
from typing import Mapping

from seshat.fabric_waves.i11_activity_network import parse_page_map

_SOURCE_SUFFIX = re.compile(
    r"(===.+\sPAGE\s+\d+\s+/\s+\d+)\s+SOURCE\s+\S+(\s+===)",
    re.MULTILINE,
)

EQUIVALENT_TO_MODEL_INPUT = "EQUIVALENT_TO_MODEL_INPUT"
INDEPENDENT_POST_EXTRACTION = "INDEPENDENT_POST_EXTRACTION"
NOT_FED_TO_MODEL = "NOT_FED_TO_MODEL"


def inner_page_texts(marked_utf8: bytes) -> dict[int, str]:
    text = marked_utf8.decode("utf-8")
    normalized = _SOURCE_SUFFIX.sub(r"\1\2", text).encode("utf-8")
    return {
        number: chunk.strip()
        for number, (_start, _end, chunk) in parse_page_map(normalized).items()
    }


def compare_inner_page_texts(
    model_pages: Mapping[int, str],
    derived_pages: Mapping[int, str],
) -> dict[str, object]:
    model_ids = set(model_pages)
    derived_ids = set(derived_pages)
    if model_ids != derived_ids:
        return {
            "status": "PAGE_COUNT_OR_NUMBERING_MISMATCH",
            "inner_page_text_equivalent": False,
            "matched_pages": (),
            "diverged_pages": tuple(sorted(model_ids ^ derived_ids)),
        }
    matched = tuple(
        sorted(page for page in model_ids if model_pages[page] == derived_pages[page])
    )
    diverged = tuple(sorted(page for page in model_ids if page not in set(matched)))
    return {
        "status": (
            "INNER_PAGE_TEXT_EQUIVALENT_WRAPPERS_MAY_DIFFER"
            if not diverged
            else "INNER_PAGE_TEXT_DIVERGES"
        ),
        "inner_page_text_equivalent": not diverged,
        "matched_pages": matched,
        "diverged_pages": diverged,
    }


def qualify_source_text_lineage(
    *,
    original_pdf_sha256: str,
    derived_page_view_sha256: str,
    extractor_version: str,
    original_model_input_page_text_sha256: str | None = None,
    model_input_pages: Mapping[int, str] | None = None,
    derived_pages: Mapping[int, str] | None = None,
) -> dict[str, object]:
    """Keep three digests distinct and state their relation.

    ``derived_page_view_sha256`` is the current extractor output. It is not
    the model-input digest unless the whole-file hashes actually match.
    """
    if not original_model_input_page_text_sha256:
        relation = NOT_FED_TO_MODEL
        page_cmp: dict[str, object] = {
            "status": "NOT_COMPARED",
            "inner_page_text_equivalent": False,
            "matched_pages": (),
            "diverged_pages": (),
        }
    elif original_model_input_page_text_sha256 == derived_page_view_sha256:
        relation = EQUIVALENT_TO_MODEL_INPUT
        page_cmp = {
            "status": "WHOLE_FILE_DIGEST_MATCH",
            "inner_page_text_equivalent": True,
            "matched_pages": (),
            "diverged_pages": (),
        }
        if model_input_pages is not None and derived_pages is not None:
            page_cmp = compare_inner_page_texts(model_input_pages, derived_pages)
            if page_cmp["inner_page_text_equivalent"] is not True:
                relation = INDEPENDENT_POST_EXTRACTION
    else:
        relation = INDEPENDENT_POST_EXTRACTION
        page_cmp = {
            "status": "WHOLE_FILE_DIGEST_MISMATCH",
            "inner_page_text_equivalent": False,
            "matched_pages": (),
            "diverged_pages": (),
        }
        if model_input_pages is not None and derived_pages is not None:
            page_cmp = compare_inner_page_texts(model_input_pages, derived_pages)

    return {
        "original_pdf_sha256": original_pdf_sha256,
        "original_model_input_page_text_sha256": (
            original_model_input_page_text_sha256 or NOT_FED_TO_MODEL
        ),
        "derived_page_view_sha256": derived_page_view_sha256,
        "extractor_version": extractor_version,
        "extraction_relation": relation,
        "derived_view_is_model_input": relation == EQUIVALENT_TO_MODEL_INPUT,
        "page_comparison": page_cmp,
    }
