"""Upload, processing and retry endpoints."""

from app.routers.sheet_music import MAX_UPLOAD_BYTES

from test_auth import start


def pdf(size=16):
    return {"pdf_file": ("score.pdf", b"%PDF" + b"0" * (size - 4), "application/pdf")}


def test_process_queues_a_job_for_the_token_owner(client, processor, alice, bob):
    res = client.post("/sheet_music/process", headers=alice.headers, files=pdf(),
                      data={"piece_id": alice.piece_id, "user_id": bob.id})
    assert res.json() == {"status": "processing_started"}
    [(_bytes, piece_id, user_id, _name)] = processor.jobs
    assert (piece_id, user_id) == (alice.piece_id, alice.id)


def test_process_rejects_oversized_uploads(client, processor, alice):
    res = client.post("/sheet_music/process", headers=alice.headers,
                      files=pdf(MAX_UPLOAD_BYTES + 1), data={"piece_id": alice.piece_id})
    assert res.status_code == 413
    assert processor.jobs == []


def test_process_requires_a_file(client, processor, alice):
    res = client.post("/sheet_music/process", headers=alice.headers,
                      data={"piece_id": alice.piece_id})
    assert res.status_code == 422
    assert processor.jobs == []


def test_retry_requeues_from_storage(client, fake, processor, alice):
    res = client.post("/sheet_music/retry", headers=alice.headers,
                      data={"piece_id": alice.piece_id})
    assert res.json() == {"status": "processing_started"}
    [(pdf_bytes, piece_id, user_id, _title)] = processor.jobs
    assert pdf_bytes.startswith(b"%PDF") and (piece_id, user_id) == (alice.piece_id, alice.id)
    assert fake.rows("pieces", id=alice.piece_id)[0]["status"] == "processing"


def test_retry_refuses_once_there_is_practice_progress(client, fake, processor, alice):
    session_id = start(client, alice)
    step = client.get("/practice/next", params={"piece_id": alice.piece_id},
                      headers=alice.headers).json()["action"]["step"]
    client.post("/practice/attempt", headers=alice.headers, json={
        "session_id": session_id, "piece_id": alice.piece_id,
        "section_id": step["section_id"], "step_key": step["key"],
        "stage": step["stage"], "self_report": "nailed"})

    res = client.post("/sheet_music/retry", headers=alice.headers,
                      data={"piece_id": alice.piece_id})
    assert "practice progress" in res.json()["error"]
    assert processor.jobs == []
    assert fake.rows("pieces", id=alice.piece_id)[0]["status"] == "ready"


def test_retry_without_a_stored_pdf(client, fake, processor, alice):
    fake.rows("pieces", id=alice.piece_id)[0]["file_path"] = None
    res = client.post("/sheet_music/retry", headers=alice.headers,
                      data={"piece_id": alice.piece_id})
    assert res.json() == {"error": "piece not found"}
    assert processor.jobs == []


def test_detector(client, alice):
    ok = client.post("/sheet_music/detector", headers=alice.headers, files=pdf())
    assert ok.json() == {"sheet_music": True}
    big = client.post("/sheet_music/detector", headers=alice.headers,
                      files=pdf(MAX_UPLOAD_BYTES + 1))
    assert big.json()["reason"] == "too_large"
