"""The service half of the model pills: which model ANSWERED, and whether it searched.

The console shows two pills at the top right: the model that answered the last request, and
``Search`` when that answer used an online search tool. Both come from response headers the kit
emits (``install_answer_provenance`` in ``api/app.py``) for whatever the model adapters NOTED as
they called. Before a request is answered the pill shows ``generator_model`` from ``/healthz``,
so that value must be the model the bound adapter calls, never one a configuration flag names
while the adapter calls another.

Here the analyst model port is bound to the deterministic stub under ``local``, and the stub
notes its own name on every proposal and narration, so an answered question names the stub. The
managed adapter is a deployment-wired placeholder that raises, so it has nothing to note. No
adapter here attaches an online search tool; the route is still proved to carry ``Search`` the day
one does, by standing a noting service in for the real one.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from hex_service_kit import provenance

from nl2sql_analytics import config
from nl2sql_analytics.adapters.local.llm import LocalAnalystLlm
from nl2sql_analytics.api import app as app_module
from nl2sql_analytics.config import LOCAL_STUB_MODEL, Settings
from nl2sql_analytics.domain.analyst_service import AnalystService

from tests import REPO_ROOT
from tests.conftest import local_settings

ANSWERED_BY = "x-answered-by"
SEARCH_USED = "x-search-used"


def _ask(api_client: TestClient, question: str = "What was total revenue by region?") -> dict:
    response = api_client.post(
        "/v1/ask", json={"question": question}, headers={"X-Dev-Persona": "auditor"}
    )
    assert response.status_code == 200, response.text
    return dict(response.headers)


def test_an_answered_question_names_the_stub_that_answered_it(api_client: TestClient) -> None:
    """Under ``local`` the pill must name the stub, the same name ``/healthz`` reports."""
    headers = _ask(api_client)
    assert headers[ANSWERED_BY] == LOCAL_STUB_MODEL
    assert headers[ANSWERED_BY] == Settings.load().generator_model
    assert SEARCH_USED not in headers, "nothing here searched, so no Search pill"


def test_a_request_that_reached_no_model_names_none(api_client: TestClient) -> None:
    """Nothing noted, nothing sent: the pill never invents a model for a model-free route."""
    response = api_client.get("/healthz")
    assert response.status_code == 200
    assert ANSWERED_BY not in response.headers
    assert SEARCH_USED not in response.headers


def test_the_stub_notes_itself_on_both_of_its_jobs() -> None:
    llm = LocalAnalystLlm(local_settings())
    with provenance.scope() as record:
        llm.propose_intent("total revenue by region", ())
    assert record.models == [LOCAL_STUB_MODEL]
    with provenance.scope() as record:
        llm.narrate({"metric": "revenue", "rows": [["APAC", 1]], "row_count": 1})
    assert record.models == [LOCAL_STUB_MODEL]
    assert record.search_used is False


class _SearchingAnalyst:
    """The real orchestrator, plus what a model adapter that searched would note while it called."""

    def __init__(self, real: AnalystService) -> None:
        self._real = real

    def answer(self, *args: object, **kwargs: object) -> object:
        provenance.note_model("fake-answering-model")
        provenance.note_search()
        return self._real.answer(*args, **kwargs)  # type: ignore[arg-type]


def test_the_route_names_the_model_that_answered_and_that_it_searched(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = app_module._analyst()
    monkeypatch.setattr(app_module, "_analyst", lambda: _SearchingAnalyst(real))
    headers = _ask(api_client)
    # Every distinct model that answered, in call order: the fake first, then the stub.
    assert headers[ANSWERED_BY].split(", ")[0] == "fake-answering-model"
    assert headers[SEARCH_USED] == "true"
    # The next request is a fresh record: an answer never leaks into a later response.
    monkeypatch.setattr(app_module, "_analyst", lambda: real)
    headers = _ask(api_client)
    assert headers[ANSWERED_BY] == LOCAL_STUB_MODEL
    assert SEARCH_USED not in headers


def test_generator_model_is_the_setting_the_adapter_reads_and_no_flag_swaps_it() -> None:
    """The latent false banner: a flag that moved the pill but not the model that answered.

    A resolver once named ``models.hard_reasoning`` when ``models.use_hard_reasoning`` was set,
    while a managed adapter called ``request.model or models.reasoning`` and never read the
    flag. The pill then named a model that never answered. The flag is gone; a stray one in a
    settings object must change nothing.
    """
    models = SimpleNamespace(
        reasoning="the-model-the-adapter-calls",
        hard_reasoning="a-model-nobody-calls",
        use_hard_reasoning=True,
    )
    named = config._model_from_settings(SimpleNamespace(models=models), "models.reasoning")
    assert named == "the-model-the-adapter-calls"


def test_the_hard_reasoning_flag_does_not_exist() -> None:
    settings_file = (REPO_ROOT / "config" / "settings.yaml").read_text(encoding="utf-8")
    assert "use_hard_reasoning" not in settings_file
    for source in sorted((REPO_ROOT / "src").rglob("*.py")):
        assert "use_hard_reasoning" not in source.read_text(encoding="utf-8"), source
