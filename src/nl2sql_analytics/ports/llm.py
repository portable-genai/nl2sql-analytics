"""AnalystLlmPort: the model's two narrow, untrusted jobs, behind the hexagon boundary.

The model PROPOSES a structured intent from a question and NARRATES a finished result. Both are
untrusted: the proposal is schema-validated and discarded on failure, the narration is checked
for groundedness and discarded on failure. The model never chooses what is answered, never
authorises a dataset, never composes SQL and never produces a figure or a verdict. Keeping both
jobs behind one port means the offline gate binds a deterministic local model and the managed
profile binds Gemini with a lazy SDK import, with no change to the domain.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

from ..domain.models import DictionaryEntry


@runtime_checkable
class AnalystLlmPort(Protocol):
    def propose_intent(
        self, question: str, hints: tuple[DictionaryEntry, ...]
    ) -> Mapping[str, Any]:
        """Propose an analytical intent as a plain mapping (validated and discarded downstream)."""
        ...

    def narrate(self, facts: Mapping[str, Any]) -> str:
        """Narrate a finished result from facts alone (grounded-checked, discarded on failure)."""
        ...
