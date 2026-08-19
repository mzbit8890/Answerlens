import asyncio
import json
from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row

from schemas.audit import AuditDelta, AuditRecord, AuditStatus, PersistedAuditResult


class AuditRepositoryError(RuntimeError):
    """Expected persistence failure at the audit repository boundary."""


class AuditRepository(Protocol):
    async def create_running_audit(self, target_url: str, category: str | None, known_competitors: list[str], previous_audit_id: UUID | None = None) -> AuditRecord: ...
    async def get_audit(self, audit_id: UUID) -> AuditRecord | None: ...
    async def complete_audit(self, audit_id: UUID, result: PersistedAuditResult, delta: AuditDelta | None) -> AuditRecord: ...
    async def fail_audit(self, audit_id: UUID, error_code: str, error_message: str) -> AuditRecord: ...


def _record(row: dict) -> AuditRecord:
    return AuditRecord.model_validate(row)


class PostgresAuditRepository:
    def __init__(self, database_url: str) -> None:
        if not database_url.strip():
            raise AuditRepositoryError("DATABASE_URL is not configured")
        self._database_url = database_url

    def _execute_sync(self, query: str, params: tuple, *, fetch: bool = True) -> dict | None:
        try:
            with psycopg.connect(self._database_url, row_factory=dict_row) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(query, params)
                    return cursor.fetchone() if fetch else None
        except psycopg.Error as exc:
            raise AuditRepositoryError("PostgreSQL audit operation failed") from exc

    async def _execute(self, query: str, params: tuple, *, fetch: bool = True) -> dict | None:
        return await asyncio.to_thread(
            self._execute_sync,
            query,
            params,
            fetch=fetch,
        )

    async def create_running_audit(self, target_url: str, category: str | None, known_competitors: list[str], previous_audit_id: UUID | None = None) -> AuditRecord:
        audit_id = uuid4()
        row = await self._execute(
            """INSERT INTO audits (id,target_url,category,known_competitors,status,previous_audit_id)
               VALUES (%s,%s,%s,%s::jsonb,%s,%s) RETURNING *""",
            (audit_id, target_url, category, json.dumps(known_competitors), AuditStatus.RUNNING.value, previous_audit_id),
        )
        assert row is not None
        return _record(row)

    async def get_audit(self, audit_id: UUID) -> AuditRecord | None:
        row = await self._execute("SELECT * FROM audits WHERE id = %s", (audit_id,))
        return _record(row) if row else None

    async def complete_audit(self, audit_id: UUID, result: PersistedAuditResult, delta: AuditDelta | None) -> AuditRecord:
        row = await self._execute(
            """UPDATE audits SET status=%s,result=%s::jsonb,delta=%s::jsonb,error_code=NULL,error_message=NULL,completed_at=%s
               WHERE id=%s RETURNING *""",
            (AuditStatus.COMPLETED.value, json.dumps(result.model_dump(mode="json")), json.dumps(delta.model_dump(mode="json")) if delta else None, datetime.now(timezone.utc), audit_id),
        )
        if row is None:
            raise AuditRepositoryError("audit disappeared while completing")
        return _record(row)

    async def fail_audit(self, audit_id: UUID, error_code: str, error_message: str) -> AuditRecord:
        row = await self._execute(
            """UPDATE audits SET status=%s,result=NULL,delta=NULL,error_code=%s,error_message=%s,completed_at=%s
               WHERE id=%s RETURNING *""",
            (AuditStatus.FAILED.value, error_code, error_message[:500], datetime.now(timezone.utc), audit_id),
        )
        if row is None:
            raise AuditRepositoryError("audit disappeared while failing")
        return _record(row)
