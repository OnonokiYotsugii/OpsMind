import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from opsmind.db.models import Employee, Equipment, Ticket

pytestmark = pytest.mark.integration
BASE = "/api/v1"
PAYLOAD = {
    "equipment_no": "EQ-10023",
    "title": "开机报警",
    "description": "今天开机后持续报警",
    "category": "electrical",
    "priority": "high",
}


def employee_id(connection, number="EMP-1002"):
    with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
        return session.scalar(select(Employee.id).where(Employee.employee_no == number))


def test_equipment_and_histories(client):
    result = client.get(f"{BASE}/equipment/EQ-10023")
    assert result.status_code == 200
    assert result.json()["equipment_no"] == "EQ-10023"
    assert result.json()["last_maintenance_at"].endswith("Z")
    history = client.get(f"{BASE}/equipment/EQ-10023/maintenance-records").json()
    assert history["items"][0]["maintenance_action"] == "更换电池并检查接线"
    assert client.get(f"{BASE}/equipment/EQ-10023/tickets").json()["items"][0]["status"] == "closed"


@pytest.mark.parametrize(
    "path,status",
    [
        ("/equipment/EQ-MISSING", 404),
        ("/equipment/EQ-MISSING/tickets", 404),
        ("/equipment/EQ-MISSING/maintenance-records", 404),
        ("/equipment/EQ-10023/tickets?limit=0", 422),
        ("/equipment/EQ-10023/maintenance-records?offset=-1", 422),
    ],
)
def test_query_failures(client, path, status):
    assert client.get(BASE + path).status_code == status


def test_full_ticket_lifecycle_persists(client, db_connection):
    created = client.post(f"{BASE}/tickets", json=PAYLOAD)
    assert created.status_code == 201
    ticket = created.json()
    assert ticket["created_by"] == employee_id(db_connection, "EMP-1001")
    path = f"{BASE}/tickets/{ticket['ticket_no']}"
    result = client.patch(
        path,
        json={
            "assigned_to": employee_id(db_connection),
            "status": "in_progress",
        },
    )
    assert result.status_code == 200
    assert (
        client.patch(path, json={"status": "resolved", "diagnosis": "接线松动"}).status_code == 200
    )
    assert client.patch(path, json={"status": "closed"}).status_code == 200
    assert client.patch(path, json={"title": "不能再改"}).status_code == 409
    with Session(bind=db_connection, join_transaction_mode="create_savepoint") as session:
        stored = session.scalar(select(Ticket).where(Ticket.ticket_no == ticket["ticket_no"]))
        assert stored.status == "closed"
        assert stored.diagnosis == "接线松动"


def test_invalid_transition_does_not_partially_update(client):
    ticket = client.post(f"{BASE}/tickets", json=PAYLOAD).json()
    result = client.patch(
        f"{BASE}/tickets/{ticket['ticket_no']}",
        json={"title": "不应保存", "status": "closed"},
    )
    assert result.status_code == 409
    history = client.get(f"{BASE}/equipment/EQ-10023/tickets").json()["items"]
    stored = next(item for item in history if item["ticket_no"] == ticket["ticket_no"])
    assert stored["title"] == PAYLOAD["title"]
    assert stored["status"] == "open"


def test_assignment_and_resolution_requirements(client, db_connection):
    ticket = client.post(f"{BASE}/tickets", json=PAYLOAD).json()
    path = f"{BASE}/tickets/{ticket['ticket_no']}"
    assert client.patch(path, json={"status": "in_progress"}).status_code == 409
    assert client.patch(path, json={"assigned_to": 999999999}).status_code == 422
    assert client.patch(path, json={"assigned_to": employee_id(db_connection)}).status_code == 200
    assert client.patch(path, json={"status": "in_progress"}).status_code == 200
    assert client.patch(path, json={"assigned_to": None}).status_code == 409
    assert client.patch(path, json={"status": "resolved"}).status_code == 409


def test_requester_cannot_update_or_assign(client, db_connection):
    client.app.state.settings.demo_employee_no = "EMP-1003"
    ticket = client.post(f"{BASE}/tickets", json=PAYLOAD)
    assert ticket.status_code == 201
    assert (
        client.patch(
            f"{BASE}/tickets/{ticket.json()['ticket_no']}", json={"title": "changed"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"{BASE}/tickets",
            json={
                **PAYLOAD,
                "assigned_to": employee_id(db_connection),
            },
        ).status_code
        == 403
    )


def test_inactive_equipment_and_actor_are_rejected(client, db_connection):
    with Session(bind=db_connection, join_transaction_mode="create_savepoint") as session:
        equipment = session.scalar(select(Equipment).where(Equipment.equipment_no == "EQ-10023"))
        equipment.status = "inactive"
        session.commit()
    assert client.post(f"{BASE}/tickets", json=PAYLOAD).status_code == 409
    client.app.state.settings.demo_employee_no = "EMP-MISSING"
    assert client.post(f"{BASE}/tickets", json=PAYLOAD).status_code == 403


def test_pagination_is_stable(client):
    numbers = [client.post(f"{BASE}/tickets", json=PAYLOAD).json()["ticket_no"] for _ in range(3)]
    assert len(set(numbers)) == 3
    first = client.get(f"{BASE}/equipment/EQ-10023/tickets?limit=2").json()["items"]
    second = client.get(f"{BASE}/equipment/EQ-10023/tickets?limit=2&offset=2").json()["items"]
    assert len(first) == len(second) == 2
    assert not {item["id"] for item in first} & {item["id"] for item in second}
    empty = client.get(f"{BASE}/equipment/EQ-10023/tickets?offset=100").json()["items"]
    assert empty == []


@pytest.mark.parametrize(
    "payload",
    [
        {**PAYLOAD, "created_by": 777},
        {**PAYLOAD, "priority": "critical"},
        {**PAYLOAD, "title": " "},
        {**PAYLOAD, "assigned_to": True},
    ],
)
def test_invalid_create(client, payload):
    assert client.post(f"{BASE}/tickets", json=payload).status_code == 422


def test_missing_ticket_and_patch_validation(client):
    assert client.patch(f"{BASE}/tickets/TK-MISSING", json={"title": "new"}).status_code == 404
    assert client.patch(f"{BASE}/tickets/TK-MISSING", json={}).status_code == 422
