import os
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from config import load_local_environment
from repositories.audit import AuditRepositoryError, PostgresAuditRepository
from schemas.audit import AuditCreateRequest, AuditRecord
from services.audit_service import AuditExecutionError, AuditNotFoundError, AuditService

app = FastAPI(title="AnswerLens API")
load_local_environment()
origins = [item.strip() for item in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if item.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"], allow_headers=["Content-Type"])


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy"}


def get_audit_service() -> AuditService:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise HTTPException(status_code=503, detail={"code": "database_not_configured", "message": "Audit persistence is not configured."})
    return AuditService(PostgresAuditRepository(database_url))


def _execution_failure(exc: AuditExecutionError) -> HTTPException:
    return HTTPException(status_code=503, detail={"code": exc.audit.error_code, "message": exc.audit.error_message, "audit": exc.audit.model_dump(mode="json")})


@app.post("/audits", response_model=AuditRecord)
async def create_audit(request: AuditCreateRequest, service: AuditService = Depends(get_audit_service)) -> AuditRecord:
    try: return await service.run(request)
    except AuditExecutionError as exc: raise _execution_failure(exc) from exc
    except AuditRepositoryError as exc: raise HTTPException(status_code=503, detail={"code": "database_unavailable", "message": "Audit persistence is temporarily unavailable."}) from exc


@app.get("/audits/{audit_id}", response_model=AuditRecord)
async def get_audit(audit_id: UUID, service: AuditService = Depends(get_audit_service)) -> AuditRecord:
    try: return await service.get(audit_id)
    except AuditNotFoundError as exc: raise HTTPException(status_code=404, detail={"code": "audit_not_found", "message": "Audit not found."}) from exc
    except AuditRepositoryError as exc: raise HTTPException(status_code=503, detail={"code": "database_unavailable", "message": "Audit persistence is temporarily unavailable."}) from exc


@app.post("/audits/{audit_id}/rerun", response_model=AuditRecord)
async def rerun_audit(audit_id: UUID, service: AuditService = Depends(get_audit_service)) -> AuditRecord:
    try: return await service.rerun(audit_id)
    except AuditNotFoundError as exc: raise HTTPException(status_code=404, detail={"code": "audit_not_found", "message": "Audit not found."}) from exc
    except AuditExecutionError as exc: raise _execution_failure(exc) from exc
    except AuditRepositoryError as exc: raise HTTPException(status_code=503, detail={"code": "database_unavailable", "message": "Audit persistence is temporarily unavailable."}) from exc
