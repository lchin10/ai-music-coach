"""The practice runtime over HTTP: happy paths, bad input, retries, failures."""

import pytest

from test_auth import start


def live_step(res):
    return res.json()["action"]["step"]


def report(client, user, session_id, step, **overrides):
    body = {
        "session_id": session_id, "piece_id": user.piece_id,
        "section_id": step["section_id"], "step_key": step["key"],
        "stage": step["stage"], "self_report": "nailed",
    }
    return client.post("/practice/attempt", json={**body, **overrides}, headers=user.headers)


@pytest.fixture
def session(client, alice):
    res = client.post("/practice/session/start", json={"piece_id": alice.piece_id},
                      headers=alice.headers)
    return res.json()["session_id"], live_step(res)


# -- reporting -------------------------------------------------------------


def test_nailed_raises_mastery_and_advances(client, fake, alice, session):
    session_id, step = session
    res = report(client, alice, session_id, step)
    assert res.status_code == 200
    assert res.json()["mastery"] > 0
    assert live_step(res)["key"] != step["key"]
    [row] = fake.rows("step_attempts", session_id=session_id)
    assert row["user_id"] == alice.id and row["self_report"] == "nailed"


def test_shaky_keeps_the_same_step_and_scores_below_nailed(client, fake, alice, bob):
    a_session = start(client, alice)
    a_step = live_step(client.get("/practice/next", params={"piece_id": alice.piece_id},
                                  headers=alice.headers))
    shaky = report(client, alice, a_session, a_step, self_report="shaky")
    assert live_step(shaky)["key"] == a_step["key"]

    b_session = start(client, bob)
    b_step = live_step(client.get("/practice/next", params={"piece_id": bob.piece_id},
                                  headers=bob.headers))
    nailed = report(client, bob, b_session, b_step)
    assert 0 < shaky.json()["mastery"] < nailed.json()["mastery"]


@pytest.mark.parametrize("overrides", [
    {"self_report": "bogus"},
    {"self_report": "struggling"},  # has its own endpoint
    {"self_report": None},
    {"seconds": -1},
    {"seconds": 10**9},
    {"tempo_reached": 0},
    {"tempo_reached": 5000},
    {"target_tempo": -5},
    {"seconds": "a while"},
])
def test_attempt_rejects_bad_input(client, fake, alice, session, overrides):
    session_id, step = session
    res = report(client, alice, session_id, step, **overrides)
    assert res.status_code == 422, res.text
    assert fake.rows("step_attempts") == []


@pytest.mark.parametrize("missing", ["session_id", "piece_id", "section_id", "step_key", "stage"])
def test_attempt_requires_every_field(client, alice, session, missing):
    session_id, step = session
    body = {"session_id": session_id, "piece_id": alice.piece_id,
            "section_id": step["section_id"], "step_key": step["key"],
            "stage": step["stage"], "self_report": "nailed"}
    del body[missing]
    assert client.post("/practice/attempt", json=body,
                       headers=alice.headers).status_code == 422


def test_client_supplied_user_id_is_ignored(client, fake, alice, bob, session):
    session_id, step = session
    res = report(client, alice, session_id, step, user_id=bob.id)
    assert res.status_code == 200
    assert fake.rows("step_attempts")[0]["user_id"] == alice.id
    assert fake.rows("section_mastery", user_id=bob.id) == []


# -- session lifecycle -----------------------------------------------------


def test_end_is_idempotent_and_first_end_wins(client, fake, alice, session):
    session_id, _ = session
    first = client.post("/practice/session/end",
                        json={"session_id": session_id, "total_seconds": 300},
                        headers=alice.headers)
    assert first.status_code == 200
    ended_at = fake.rows("practice_sessions", id=session_id)[0]["ended_at"]
    assert ended_at is not None

    again = client.post("/practice/session/end",
                        json={"session_id": session_id, "total_seconds": 999},
                        headers=alice.headers)
    assert again.status_code == 200
    row = fake.rows("practice_sessions", id=session_id)[0]
    assert (row["ended_at"], row["total_seconds"]) == (ended_at, 300)


@pytest.mark.parametrize("seconds", [-1, 10**9])
def test_end_rejects_impossible_durations(client, alice, session, seconds):
    session_id, _ = session
    res = client.post("/practice/session/end",
                      json={"session_id": session_id, "total_seconds": seconds},
                      headers=alice.headers)
    assert res.status_code == 422


def test_unknown_session_is_404(client, alice):
    res = client.post("/practice/session/end",
                      json={"session_id": "00000000-0000-0000-0000-000000000000"},
                      headers=alice.headers)
    assert res.status_code == 404


def test_piece_with_no_sections_starts_with_nothing_queued(client, fake, alice):
    fake.store["sections"] = [s for s in fake.store["sections"]
                              if s["piece_id"] != alice.piece_id]
    res = client.post("/practice/session/start", json={"piece_id": alice.piece_id},
                      headers=alice.headers)
    assert res.status_code == 200
    assert res.json()["sections"] == []
    assert res.json()["action"]["step"] is None


def test_step_lookup(client, alice, session):
    _, step = session
    found = client.get("/practice/step", params={"piece_id": alice.piece_id,
                                                 "step_key": step["key"]},
                       headers=alice.headers)
    assert found.json()["step"]["key"] == step["key"]
    missing = client.get("/practice/step", params={"piece_id": alice.piece_id,
                                                   "step_key": "nope"},
                         headers=alice.headers)
    assert missing.json() == {"error": "step not found"}


# -- skip ------------------------------------------------------------------


def test_skip_stage_clears_the_stage_once(client, fake, alice, session):
    session_id, step = session
    body = {"session_id": session_id, "piece_id": alice.piece_id,
            "section_id": step["section_id"], "stage": step["stage"]}
    assert client.post("/practice/skip_stage", json=body, headers=alice.headers).status_code == 200
    skipped = fake.rows("step_attempts", skipped=True)
    assert skipped and all(r["stage"] == step["stage"] for r in skipped)

    client.post("/practice/skip_stage", json=body, headers=alice.headers)
    assert len(fake.rows("step_attempts", skipped=True)) == len(skipped)


def test_skip_unknown_stage_writes_nothing(client, fake, alice, session):
    session_id, step = session
    res = client.post("/practice/skip_stage", headers=alice.headers, json={
        "session_id": session_id, "piece_id": alice.piece_id,
        "section_id": step["section_id"], "stage": "nonsense"})
    assert res.status_code == 200
    assert fake.rows("step_attempts") == []


# -- struggling ------------------------------------------------------------


def struggle(client, user, session_id, step):
    return client.post("/practice/struggling", headers=user.headers, json={
        "session_id": session_id, "piece_id": user.piece_id,
        "section_id": step["section_id"], "step_key": step["key"], "stage": step["stage"]})


def test_first_struggle_narrows_without_a_model_call(client, fake, alice, session, llm):
    session_id, step = session
    res = struggle(client, alice, session_id, step)
    assert res.status_code == 200
    assert llm.count == 0
    assert fake.rows("plan_steps", source="remediation")
    assert fake.rows("step_attempts", self_report="struggling")


def test_second_struggle_asks_the_model(client, fake, alice, session, llm):
    session_id, step = session
    struggle(client, alice, session_id, step)
    before = len(fake.rows("plan_steps", source="remediation"))
    res = struggle(client, alice, session_id, step)
    assert res.status_code == 200
    assert llm.count == 1
    assert len(fake.rows("plan_steps", source="remediation")) > before


def test_model_failure_falls_back_to_narrowing(client, fake, alice, session, llm):
    llm.error = RuntimeError("anthropic is down")
    session_id, step = session
    struggle(client, alice, session_id, step)
    before = len(fake.rows("plan_steps", source="remediation"))
    res = struggle(client, alice, session_id, step)
    assert res.status_code == 200
    assert llm.count == 1
    assert len(fake.rows("plan_steps", source="remediation")) > before


def test_struggle_on_unknown_step(client, fake, alice, session):
    session_id, step = session
    res = struggle(client, alice, session_id, {**step, "key": "nope"})
    assert res.json() == {"error": "step not found"}
    assert fake.rows("step_attempts") == []


def test_struggle_without_a_plan(client, fake, alice, session):
    fake.store["practice_plans"] = []
    session_id, step = session
    assert struggle(client, alice, session_id, step).json() == {"error": "no plan for this piece"}
