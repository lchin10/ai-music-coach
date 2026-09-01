"""Graph state.

The only subtle part is `sections`: the fan-out writes one entry per branch,
so it needs an additive reducer. Branches finish out of order, so nothing may
depend on arrival order — the validator sorts by start_measure.
"""

import operator
from typing import Annotated, Any, Optional, TypedDict


def replace_sections(current: list, incoming: list) -> list:
    """Reducer for the fan-out.

    Fan-out branches append. A revision pass re-runs `design_drills` for a
    subset of sections and must overwrite by index rather than append, or the
    second pass would duplicate every section it touched.
    """
    if incoming == []:  # explicit reset before a revision pass
        return []
    merged = {s["index"]: s for s in current}
    for section in incoming:
        merged[section["index"]] = section
    return [merged[i] for i in sorted(merged)]


class PlanState(TypedDict, total=False):
    # --- inputs ---
    piece_id: str
    user_id: Optional[str]
    profile: dict
    features: dict

    # --- segmenter output ---
    structural_summary: str
    boundaries: list  # [{index, title, start_measure, end_measure, boundary_rationale}]

    # --- fan-out output ---
    sections: Annotated[list, replace_sections]

    # --- review loop ---
    validation: dict
    critique: dict
    feedback: dict  # section_index -> feedback string
    revisions: Annotated[int, operator.add]

    # --- terminal ---
    error: Optional[str]
    result: Any
