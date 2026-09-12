import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from opsmind.db.models import Employee, Equipment, MaintenanceRecord, Ticket
from opsmind.db.seed import seed_demo

pytestmark = pytest.mark.integration


def test_seed_is_repeatable_and_does_not_overwrite(db_connection):
    with Session(bind=db_connection, join_transaction_mode="create_savepoint") as session:
        equipment = session.scalar(select(Equipment))
        equipment.location = "用户修改的位置"
        session.commit()
        assert all(count == 0 for count in seed_demo(session).values())
        assert session.scalar(select(Equipment)).location == "用户修改的位置"
        assert session.scalar(select(func.count()).select_from(MaintenanceRecord)) == 1


@pytest.mark.parametrize("violation", ["unique", "foreign_key", "check", "restrict_delete"])
def test_mysql_enforces_constraints(db_connection, violation):
    with Session(bind=db_connection, join_transaction_mode="create_savepoint") as session:
        error_type = OperationalError if violation == "check" else IntegrityError
        with pytest.raises(error_type) as raised:
            with session.begin():
                if violation == "unique":
                    session.add(
                        Employee(
                            employee_no="EMP-1001",
                            name="duplicate",
                            department="test",
                            role="admin",
                            status="active",
                        )
                    )
                elif violation == "foreign_key":
                    session.add(
                        MaintenanceRecord(
                            equipment_id=99999999,
                            fault_description="test",
                            maintenance_action="test",
                            result="test",
                            maintained_by=session.scalar(select(Employee.id).limit(1)),
                            maintenance_at=session.scalar(select(MaintenanceRecord.maintenance_at)),
                        )
                    )
                elif violation == "check":
                    session.scalar(select(Equipment)).status = "INVALID"
                else:
                    session.delete(session.scalar(select(Equipment)))
                session.flush()
        expected = {"unique": 1062, "foreign_key": 1452, "check": 3819, "restrict_delete": 1451}
        assert raised.value.orig.args[0] == expected[violation]
        assert session.scalar(select(func.count()).select_from(Equipment)) == 1


def test_failed_multi_write_rolls_back_everything(db_connection):
    with Session(bind=db_connection, join_transaction_mode="create_savepoint") as session:
        with pytest.raises(IntegrityError):
            with session.begin():
                ticket = session.scalar(select(Ticket))
                ticket.title = "should be rolled back"
                session.flush()
                session.add(
                    Employee(
                        employee_no="EMP-1001",
                        name="duplicate",
                        department="test",
                        role="admin",
                        status="active",
                    )
                )
                session.flush()
        assert session.scalar(select(Ticket)).title == "供电异常维修"
