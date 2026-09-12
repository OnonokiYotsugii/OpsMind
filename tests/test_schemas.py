import pytest
from pydantic import ValidationError

from opsmind.schemas.business import TicketCreate, TicketUpdate


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"title": None},
        {"status": None},
        {"priority": "critical"},
        {"title": "   "},
        {"created_by": 17},
        {"equipment_no": "EQ-OTHER"},
        {"assigned_to": True},
        {"description": "x" * 10001},
    ],
)
def test_invalid_patch_is_rejected(payload):
    with pytest.raises(ValidationError):
        TicketUpdate(**payload)


def test_patch_distinguishes_omitted_and_explicit_null():
    assert TicketUpdate(title="New title").model_dump(exclude_unset=True) == {"title": "New title"}
    assert TicketUpdate(assigned_to=None).model_dump(exclude_unset=True) == {"assigned_to": None}


def test_client_cannot_forge_creator():
    with pytest.raises(ValidationError):
        TicketCreate(
            equipment_no="EQ-10023",
            title="Alarm",
            description="Alarm at startup",
            category="electrical",
            created_by=999,
        )
