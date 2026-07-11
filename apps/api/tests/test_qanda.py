"""Listing Q&A (PRD §7.2): guardians ask questions on a listing, the provider
answers, everyone reads. Structured — one question, one provider reply."""

import uuid

from fastapi.testclient import TestClient


def _auth(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


def _signup(client: TestClient, name: str | None = None) -> str:
    email = f"u-{uuid.uuid4().hex[:8]}@example.com"
    return client.post(
        "/api/v1/identity/signup",
        json={"email": email, "password": "supersecret", "full_name": name},
    ).json()["access_token"]


def _org_and_program(client: TestClient, owner: str) -> tuple[str, str]:
    org_id = client.post(
        "/api/v1/org", headers=_auth(owner), json={"name": f"Org {uuid.uuid4().hex[:5]}"}
    ).json()["id"]
    program_id = client.post(
        "/api/v1/catalog/programs",
        headers=_auth(owner),
        json={"organisation_id": org_id, "title": "Camp", "category": "art"},
    ).json()["id"]
    return org_id, program_id


def _ask(client: TestClient, guardian: str, program_id: str, body: str):
    return client.post(
        f"/api/v1/qanda/programs/{program_id}/questions",
        headers=_auth(guardian),
        json={"body": body},
    )


def test_ask_answer_and_public_read(client: TestClient) -> None:
    owner = _signup(client)
    org_id, program_id = _org_and_program(client, owner)
    parent = _signup(client, name="Amara Lee")

    asked = _ask(client, parent, program_id, "Do you provide lunch?")
    assert asked.status_code == 201, asked.text
    q = asked.json()
    assert q["answer"] is None
    assert q["asker_label"] == "Amara"  # first name only

    # Publicly visible (no auth), unanswered.
    public = client.get(f"/api/v1/qanda/programs/{program_id}/questions").json()
    assert len(public) == 1
    assert public[0]["answer"] is None

    # Provider answers.
    answered = client.post(
        f"/api/v1/qanda/questions/{q['id']}/answer",
        headers=_auth(owner),
        json={"answer": "Yes — a nut-free lunch is included."},
    )
    assert answered.status_code == 200
    assert answered.json()["answer"] == "Yes — a nut-free lunch is included."

    public = client.get(f"/api/v1/qanda/programs/{program_id}/questions").json()
    assert public[0]["answer"] == "Yes — a nut-free lunch is included."


def test_only_provider_can_answer(client: TestClient) -> None:
    owner, outsider, parent = _signup(client), _signup(client), _signup(client)
    _org_id, program_id = _org_and_program(client, owner)
    q = _ask(client, parent, program_id, "What ages?").json()
    resp = client.post(
        f"/api/v1/qanda/questions/{q['id']}/answer",
        headers=_auth(outsider),
        json={"answer": "hi"},
    )
    assert resp.status_code == 403


def test_provider_inbox_lists_unanswered_first(client: TestClient) -> None:
    owner, outsider, parent = _signup(client), _signup(client), _signup(client)
    org_id, program_id = _org_and_program(client, owner)
    first = _ask(client, parent, program_id, "Q1").json()
    _ask(client, parent, program_id, "Q2")
    # Answer the first; it should sort after the still-unanswered one.
    client.post(
        f"/api/v1/qanda/questions/{first['id']}/answer",
        headers=_auth(owner),
        json={"answer": "A1"},
    )
    inbox = client.get(
        f"/api/v1/qanda/provider/{org_id}/questions", headers=_auth(owner)
    ).json()
    assert len(inbox) == 2
    assert inbox[0]["answer"] is None  # unanswered first

    assert (
        client.get(
            f"/api/v1/qanda/provider/{org_id}/questions", headers=_auth(outsider)
        ).status_code
        == 403
    )


def test_ask_on_unknown_listing_404(client: TestClient) -> None:
    parent = _signup(client)
    assert _ask(client, parent, str(uuid.uuid4()), "hi?").status_code == 404
