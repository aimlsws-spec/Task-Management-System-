from tests.conftest import as_user


def test_generic_term_recommendation_ready_directly(client, as_user):
    headers = as_user("owner")
    payload = {
        "title": "HRMS employee attendance module",
        "company_id": 1,
        "priority": "high",
        "target_type": "task",
    }
    r = client.post("/api/v1/ai/recommend", headers=headers, json=payload)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "READY"
    assert data["missing_entity"] is None
    assert "description" in data["suggestions"]
    assert "special_note" in data["suggestions"]
    assert "HRMS" in data["suggestions"]["description"] or "attendance" in data["suggestions"]["description"].lower()


def test_unknown_entity_challenge_and_learning_cycle(client, as_user):
    headers = as_user("owner")

    # 1. Unrecognized term "Elala" triggers challenge
    payload = {
        "title": "Elala UI changes",
        "company_id": 1,
        "priority": "medium",
        "target_type": "task",
    }
    r = client.post("/api/v1/ai/recommend", headers=headers, json=payload)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "NEEDS_CONTEXT"
    assert data["missing_entity"] == "Elala"
    assert "Elala" in data["prompt_question"]

    # 2. Learn entity "Elala" for company 1
    learn_payload = {
        "company_id": 1,
        "entity_name": "Elala",
        "description": "B2B jewelry eCommerce mobile app and admin portal",
        "tech_stack": "Flutter, Node.js",
        "default_notes": "Verify checkout flow across both Android and iOS devices",
    }
    r_learn = client.post("/api/v1/ai/learn-entity", headers=headers, json=learn_payload)
    assert r_learn.status_code == 200, r_learn.text
    ent = r_learn.json()
    assert ent["entity_key"] == "elala"
    assert ent["entity_name"] == "Elala"

    # 3. Now recommendation for "Elala UI changes" succeeds immediately!
    r2 = client.post("/api/v1/ai/recommend", headers=headers, json=payload)
    assert r2.status_code == 200, r2.text
    data2 = r2.json()
    assert data2["status"] == "READY"
    assert data2["missing_entity"] is None
    assert "Elala" in data2["suggestions"]["description"]


def test_company_knowledge_isolation(client, as_user, seeded):
    # Ensure company 2 exists
    from app.modules.org.models import Company
    with seeded() as s:
        comp2 = s.query(Company).filter_by(code="comp2_ai").first()
        if not comp2:
            comp2 = Company(name="Company 2 AI", code="comp2_ai")
            s.add(comp2)
            s.commit()
            comp2_id = comp2.id
        else:
            comp2_id = comp2.id

    headers = as_user("owner")

    # In Company 2, "Elala" was never learned, so it must prompt for context!
    payload_comp2 = {
        "title": "Elala UI changes",
        "company_id": comp2_id,
        "target_type": "task",
    }
    r = client.post("/api/v1/ai/recommend", headers=headers, json=payload_comp2)
    assert r.status_code == 200
    assert r.json()["status"] == "NEEDS_CONTEXT"
    assert r.json()["missing_entity"] == "Elala"


def test_knowledge_crud_and_permissions(client, as_user):
    headers_owner = as_user("owner")
    headers_emp = as_user("abc")

    # 1. Learn entity via owner
    r = client.post(
        "/api/v1/ai/learn-entity",
        headers=headers_owner,
        json={"company_id": 1, "entity_name": "TestGlossary", "description": "Internal test glossary product"},
    )
    assert r.status_code == 200
    ent_id = r.json()["id"]

    # 2. List entities
    r_list = client.get("/api/v1/ai/entities?company_id=1", headers=headers_owner)
    assert r_list.status_code == 200
    names = [e["entity_name"] for e in r_list.json()]
    assert "TestGlossary" in names

    # 3. Regular employee cannot delete knowledge entity
    r_del_fail = client.delete(f"/api/v1/ai/entities/{ent_id}?company_id=1", headers=headers_emp)
    assert r_del_fail.status_code == 403

    # 4. Owner can delete
    r_del_ok = client.delete(f"/api/v1/ai/entities/{ent_id}?company_id=1", headers=headers_owner)
    assert r_del_ok.status_code == 204
