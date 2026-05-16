"""Critique-Pass evaluation track. METHODOLOGY s13.

The CANONICAL_CRITIQUE_PROMPT is locked per s13.2. Changes require a methodology
version bump and a re-run, the same as the per-task canonical prompts. Three
deliberate design choices captured in the wording:

1. "Repeat it exactly" frames no-change as a valid first-class outcome, reducing
   sycophancy pressure toward unnecessary revision.
2. "No commentary" preserves the existing parser contract from the v0.1 tasks;
   the post-critique output is parsed identically to a no-critique attempt.
3. Zero rubric, zero validator hints, zero per-provider tuning per s6
   portability rules.

The critique prompt is appended to the original prompt + first-leg output to
form the second-leg conversation. The runner builds the second-leg prompt; this
module just owns the canonical text and a small helper for assembling it.
"""

from __future__ import annotations

CANONICAL_CRITIQUE_PROMPT: str = (
    "Review your previous answer for correctness and adherence to the requested format. "
    "If it is already correct, repeat it exactly. "
    "If not, output the corrected version. "
    "Output only the final answer with no commentary."
)


def build_critique_followup_prompt(original_prompt: str, first_leg_output: str) -> str:
    """Compose the second-leg prompt: original task prompt, the model's first-leg
    output, then the locked canonical critique prompt.

    The format mirrors `runner._build_retry_prompt` so the wire-level conversation
    shape is the same as a normal retry (provider sees a single user turn
    containing all context). Adapter abstractions remain unchanged; no new
    multi-turn API surface is required.
    """
    return (
        f"{original_prompt}"
        f"\n\nPrevious response:\n{first_leg_output}\n\n"
        f"{CANONICAL_CRITIQUE_PROMPT}"
    )
