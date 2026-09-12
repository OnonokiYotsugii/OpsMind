from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from opsmind.core.errors import BusinessError


def get_session(request: Request) -> Iterator[Session]:
    factory = request.app.state.session_factory
    if factory is None:
        raise BusinessError("database_unavailable", "Database is not configured.", 503)
    with factory() as session:
        yield session


def get_demo_actor(request: Request) -> str:
    return request.app.state.settings.demo_employee_no


DatabaseSession = Annotated[Session, Depends(get_session)]
DemoActor = Annotated[str, Depends(get_demo_actor)]
