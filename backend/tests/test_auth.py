"""Every endpoint: who may call it, and on whose data.

The backend uses the service-role key, so these tests are the only thing
standing between one user and another user's practice history.
"""

import pytest

PDF = {"pdf_file": ("score.pdf", b"%PDF-1.4 fake", "application/pdf")}


def start(client, user):
    res = client.post("/practice/session/start", json={"piece_id": user.piece_id},
                      headers=user.headers)
    assert res.status_code == 200, res.text
    return res.json()["session_id"]


def first_step_key(client, user):
    res = client.get("/practice/next", params={"piece_id": user.piece_id}, headers=user.headers)
    return res.json()["action"]["step"]["key"]


# Each builder takes the resource owner (and their session) and returns the
# request to make. Calling it with another user's headers is the IDOR test.
ROUTES = {
    "start": lambda o, s: ("POST", "/practice/session/start",
                           {"json": {"piece_id": o.piece_id}}),
    "next": lambda o, s: ("GET", "/practice/next", {"params": {"piece_id": o.piece_id}}),
    "next+session": lambda o, s: ("GET", "/practice/next",
                                  {"params": {"piece_id": o.piece_id, "session_id": s}}),
    "step": lambda o, s: ("GET", "/practice/step",
                          {"params": {"piece_id": o.piece_id, "step_key": "x"}}),
    "attempt": lambda o, s: ("POST", "/practice/attempt", {"json": {
        "session_id": s, "piece_id": o.piece_id, "section_id": o.sections[0]["id"],
        "step_key": "x", "stage": "notes", "self_report": "nailed"}}),
    "skip_stage": lambda o, s: ("POST", "/practice/skip_stage", {"json": {
        "session_id": s, "piece_id": o.piece_id, "section_id": o.sections[0]["id"],
        "stage": "notes"}}),
    "struggling": lambda o, s: ("POST", "/practice/struggling", {"json": {
        "session_id": s, "piece_id": o.piece_id, "section_id": o.sections[0]["id"],
        "step_key": "x", "stage": "notes"}}),
    "end": lambda o, s: ("POST", "/practice/session/end", {"json": {"session_id": s}}),
    "process": lambda o, s: ("POST", "/sheet_music/process",
                             {"data": {"piece_id": o.piece_id}, "files": PDF}),
    "retry": lambda o, s: ("POST", "/sheet_music/retry", {"data": {"piece_id": o.piece_id}}),
}
UNSCOPED = {
    "schema": ("GET", "/sheet_music/schema", {}),
    "detector": ("POST", "/sheet_music/detector", {"files": PDF}),
}


def every_route(owner, session_id):
    return [ROUTES[name](owner, session_id) for name in ROUTES] + list(UNSCOPED.values())


@pytest.mark.parametrize("headers", [
    {},
    {"Authorization": ""},
    {"Authorization": "Bearer"},
    {"Authorization": "Basic dXNlcjpwYXNz"},
    {"Authorization": "Bearer not-a-real-token"},
])
def test_every_route_rejects_missing_or_bad_tokens(client, alice, headers):
    session_id = start(client, alice)
    for method, path, kwargs in every_route(alice, session_id):
        res = client.request(method, path, headers=headers, **kwargs)
        assert res.status_code == 401, (method, path, headers, res.text)


@pytest.mark.parametrize("name", sorted(ROUTES))
def test_another_users_resource_is_404(client, alice, bob, name):
    bobs_session = start(client, bob)
    method, path, kwargs = ROUTES[name](bob, bobs_session)
    res = client.request(method, path, headers=alice.headers, **kwargs)
    assert res.status_code == 404, res.text


@pytest.mark.parametrize("name", ["attempt", "skip_stage", "struggling", "next+session"])
def test_own_piece_with_another_users_session_is_404(client, alice, bob, name):
    bobs_session = start(client, bob)
    method, path, kwargs = ROUTES[name](alice, bobs_session)
    res = client.request(method, path, headers=alice.headers, **kwargs)
    assert res.status_code == 404, res.text


def test_another_users_session_cannot_be_ended(client, fake, alice, bob):
    bobs_session = start(client, bob)
    res = client.post("/practice/session/end", json={"session_id": bobs_session},
                      headers=alice.headers)
    assert res.status_code == 404
    assert fake.rows("practice_sessions", id=bobs_session)[0]["ended_at"] is None


def test_section_from_another_piece_is_404(client, alice, bob):
    session_id = start(client, alice)
    res = client.post("/practice/attempt", headers=alice.headers, json={
        "session_id": session_id, "piece_id": alice.piece_id,
        "section_id": bob.sections[0]["id"], "step_key": "x", "stage": "notes",
        "self_report": "nailed"})
    assert res.status_code == 404


@pytest.mark.parametrize("bad_id", ["", "not-a-uuid", "1; drop table pieces", "0" * 36])
def test_malformed_ids_are_404_not_500(client, alice, bad_id):
    res = client.post("/practice/session/start", json={"piece_id": bad_id},
                      headers=alice.headers)
    assert res.status_code == 404


def test_owner_reaches_every_route(client, alice, llm):
    session_id = start(client, alice)
    step_key = first_step_key(client, alice)
    for name, build in ROUTES.items():
        method, path, kwargs = build(alice, session_id)
        if "json" in kwargs and "step_key" in kwargs["json"]:
            kwargs["json"]["step_key"] = step_key
        res = client.request(method, path, headers=alice.headers, **kwargs)
        assert res.status_code == 200, (name, res.text)
    for method, path, kwargs in UNSCOPED.values():
        assert client.request(method, path, headers=alice.headers, **kwargs).status_code == 200


def test_token_is_cached_but_revocation_is_not_forever(client, fake, alice, monkeypatch):
    from app import auth

    start(client, alice)
    del fake.tokens[alice.token]
    # Inside the cache window the token still works...
    assert client.get("/practice/next", params={"piece_id": alice.piece_id},
                      headers=alice.headers).status_code == 200
    # ...and after it, the revoked token is refused.
    monkeypatch.setattr(auth, "CACHE_SECONDS", 0)
    assert client.get("/practice/next", params={"piece_id": alice.piece_id},
                      headers=alice.headers).status_code == 401


def test_test_endpoint_is_gone(client, alice):
    res = client.post("/sheet_music/create_section", data={"piece_id": alice.piece_id},
                      headers=alice.headers)
    assert res.status_code in (404, 405)
