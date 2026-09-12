"""Small deterministic dataset. Repeated sequential runs preserve existing rows."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from opsmind.db.models import Employee, Equipment, MaintenanceRecord, Ticket

DEMO_MAINTAINED_AT = datetime(2026, 9, 1, 8, 0)


def seed_demo(session: Session) -> dict[str, int]:
    counts = {"employees": 0, "equipment": 0, "maintenance_records": 0, "tickets": 0}
    with session.begin():
        employees = {}
        for number, name, role in [
            ("EMP-1001", "演示管理员", "admin"),
            ("EMP-1002", "维修工程师", "technician"),
            ("EMP-1003", "设备使用人", "requester"),
        ]:
            employee = session.scalar(select(Employee).where(Employee.employee_no == number))
            if employee is None:
                employee = Employee(
                    employee_no=number,
                    name=name,
                    department="设备运维部",
                    role=role,
                    status="active",
                )
                session.add(employee)
                session.flush()
                counts["employees"] += 1
            employees[number] = employee

        equipment = session.scalar(select(Equipment).where(Equipment.equipment_no == "EQ-10023"))
        if equipment is None:
            equipment = Equipment(
                equipment_no="EQ-10023",
                name="演示供电设备",
                model="DEMO-24V",
                manufacturer="示例制造商",
                status="active",
                location="A栋一楼",
            )
            session.add(equipment)
            session.flush()
            counts["equipment"] += 1

        maintenance = session.scalar(
            select(MaintenanceRecord).where(
                MaintenanceRecord.equipment_id == equipment.id,
                MaintenanceRecord.maintenance_at == DEMO_MAINTAINED_AT,
            )
        )
        if maintenance is None:
            session.add(
                MaintenanceRecord(
                    equipment_id=equipment.id,
                    fault_description="供电异常，设备间歇性报警",
                    maintenance_action="更换电池并检查接线",
                    result="维修后测试正常",
                    maintained_by=employees["EMP-1002"].id,
                    maintenance_at=DEMO_MAINTAINED_AT,
                )
            )
            # New historical records must not move the aggregate timestamp backwards.
            if equipment.last_maintenance_at is None or (
                equipment.last_maintenance_at < DEMO_MAINTAINED_AT
            ):
                equipment.last_maintenance_at = DEMO_MAINTAINED_AT
            counts["maintenance_records"] += 1

        if session.scalar(select(Ticket).where(Ticket.ticket_no == "TK-DEMO-0001")) is None:
            session.add(
                Ticket(
                    ticket_no="TK-DEMO-0001",
                    equipment_id=equipment.id,
                    title="供电异常维修",
                    description="设备出现间歇报警，安排检查",
                    category="electrical",
                    priority="medium",
                    status="closed",
                    diagnosis="电池老化，更换后测试正常",
                    created_by=employees["EMP-1001"].id,
                    assigned_to=employees["EMP-1002"].id,
                )
            )
            counts["tickets"] += 1
    return counts
