"""Phase 7: the task discussion: comments, questions, replies, @mentions and who gets pinged."""

from .helpers import API, at, make
from .test_notifications import by_user, relay


def seeded_user_id(seeded, email):
    from sqlalchemy import select

    from app.modules.auth.models import User

    with seeded() as s:
        return s.scalar(select(User.id).where(User.email == email))


def post(client, as_user, who, tid, body="Is the staging server ready?", **over):
    return client.post(f"{API}/tasks/{tid}/comments", headers=as_user(who), json={"kind": "comment", "body": body} | over)


def uid(client, as_user, tid, name, who="devhead"):
    return next(m["user_id"] for m in client.get(f"{API}/tasks/{tid}/mentionable", headers=as_user(who)).json() if m["full_name"] == name)


def fresh(client, as_user, seeded):
    at(0)
    return make(client, as_user, seeded)


def test_comments_are_threaded_and_ordered(client, as_user, seeded):
    t = fresh(client, as_user, seeded)
    c = post(client, as_user, "abc", t["id"], "Starting with the login page")
    assert c.status_code == 201 and c.json()["kind"] == "comment" and c.json()["author"] == "ABC"
    r = post(client, as_user, "devhead", t["id"], "Sounds good", kind="comment", parent_id=c.json()["id"])
    assert r.json()["kind"] == "reply" and r.json()["parent_id"] == c.json()["id"]
    items = client.get(f"{API}/tasks/{t['id']}/comments", headers=as_user("owner")).json()
    assert [i["id"] for i in items] == [c.json()["id"], r.json()["id"]]


def test_validation(client, as_user, seeded):
    t = fresh(client, as_user, seeded)
    assert post(client, as_user, "abc", t["id"], "   ").status_code == 422
    assert post(client, as_user, "abc", t["id"], kind="shout").status_code == 422
    assert post(client, as_user, "abc", t["id"], parent_id=99999).json()["code"] == "INVALID_PARENT"
    assert post(client, as_user, "abc", t["id"], attachment_id=99999).json()["code"] == "INVALID_ATTACHMENT"
    assert post(client, as_user, "abc", t["id"], author_user_id=1).status_code == 422  # no mass assignment
    other = make(client, as_user, seeded, title="Another task")
    foreign = post(client, as_user, "abc", other["id"]).json()
    assert post(client, as_user, "abc", t["id"], parent_id=foreign["id"]).json()["code"] == "INVALID_PARENT"  # a reply stays in its own task


def test_only_people_with_a_stake_can_join_the_discussion(client, as_user, seeded):
    t = fresh(client, as_user, seeded)
    assert post(client, as_user, "hrhead", t["id"]).status_code == 404
    assert post(client, as_user, "frontend", t["id"]).status_code in (403, 404)
    assert post(client, as_user, "admin", t["id"]).status_code in (403, 404)
    assert client.get(f"{API}/tasks/{t['id']}/comments", headers=as_user("hrhead")).status_code == 404
    for who in ("abc", "devhead", "manager", "ceo", "owner"):
        assert post(client, as_user, who, t["id"], f"Hello from {who}").status_code == 201, who


def test_mentions_are_limited_to_the_people_involved(client, as_user, seeded):
    t = fresh(client, as_user, seeded)
    people = {m["full_name"] for m in client.get(f"{API}/tasks/{t['id']}/mentionable", headers=as_user("abc")).json()}
    assert "ABC" not in people and "Developers Head" in people and len(people) >= 3
    outsider = seeded_user_id(seeded, "hrhead@demo.example.com")
    r = post(client, as_user, "abc", t["id"], mentions=[outsider])
    assert r.status_code == 422 and r.json()["code"] == "INVALID_MENTION"
    me = uid(client, as_user, t["id"], "Developers Head", who="abc")
    assert post(client, as_user, "abc", t["id"], mentions=[me]).json()["mentions"][0]["full_name"] == "Developers Head"


def test_mentioned_people_and_the_assigner_are_notified(client, as_user, seeded):
    t = fresh(client, as_user, seeded)
    ceo = seeded_user_id(seeded, "ceo@demo.example.com")
    post(client, as_user, "abc", t["id"], "Need a decision on the design", mentions=[ceo])
    relay(seeded)
    got = by_user(seeded, "COMMENT_ADDED")
    assert "abc" not in got  # not told about their own comment
    assert "owner" in got  # the owner assigned it
    assert "ceo" in got and "Need a decision" in got["ceo"][0].body


def test_questions_reach_the_assigner_and_the_line_manager(client, as_user, seeded):
    t = fresh(client, as_user, seeded)
    post(client, as_user, "abc", t["id"], "Which API version should I use?", kind="question")
    relay(seeded)
    got = by_user(seeded, "QUESTION_ASKED")
    assert {"owner", "devhead"} <= set(got) and "abc" not in got
    assert "Which API version" in got["owner"][0].body


def test_replying_pings_the_author_of_the_original(client, as_user, seeded):
    t = fresh(client, as_user, seeded)
    q = post(client, as_user, "abc", t["id"], "Which API version?", kind="question").json()
    relay(seeded)
    post(client, as_user, "devhead", t["id"], "Use version 2", parent_id=q["id"])
    relay(seeded)
    got = by_user(seeded, "COMMENT_ADDED")
    assert "abc" in got and "Reply" in got["abc"][0].title


def test_edit_window_and_authorship(client, as_user, seeded):
    t = fresh(client, as_user, seeded)
    c = post(client, as_user, "abc", t["id"], "Typo hrere").json()
    assert client.patch(f"{API}/comments/{c['id']}", headers=as_user("devhead"), json={"body": "Hijack"}).status_code == 403
    assert client.patch(f"{API}/comments/{c['id']}", headers=as_user("hrhead"), json={"body": "Hijack"}).status_code == 404
    r = client.patch(f"{API}/comments/{c['id']}", headers=as_user("abc"), json={"body": "Typo here"})
    assert r.status_code == 200 and r.json()["body"] == "Typo here" and r.json()["edited"] is True
    assert client.patch(f"{API}/comments/{c['id']}", headers=as_user("abc"), json={"body": " "}).status_code == 422
    at(11)  # eleven minutes later
    r = client.patch(f"{API}/comments/{c['id']}", headers=as_user("abc"), json={"body": "Too late"})
    assert r.status_code == 409 and r.json()["code"] == "EDIT_WINDOW_CLOSED"
    audit = client.get(f"{API}/tasks/{t['id']}/timeline", headers=as_user("owner")).json()
    assert any(a["action"] == "COMMENT_EDITED" for a in (audit if isinstance(audit, list) else audit.get("items", audit.get("events", []))))


def test_comments_cannot_be_deleted(client, as_user, seeded):
    t = fresh(client, as_user, seeded)
    c = post(client, as_user, "abc", t["id"]).json()
    assert client.delete(f"{API}/comments/{c['id']}", headers=as_user("owner")).status_code in (404, 405)
