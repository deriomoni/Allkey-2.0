import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import Base, engine
from app.auth.router import router as auth_router
from app.users.router import router as users_router
from app.reconciliation.router import router as reconciliation_router, cleanup_task
from app.licenses.router import router as licenses_router
from app.settings.router import router as settings_router
from app.services.router import router as services_router, seed_services
from app.personnel.router import router as personnel_router
from app.personnel.crud import crud_router as personnel_crud_router
from app.personnel.schema_sync import ensure_personnel_schema
from app.f10104.router import router as f10104_router
from app.rates.router import router as rates_router
from app.changelog.router import router as changelog_router, seed_changelog
from app.database import SessionLocal
# Import models so they are registered with Base.metadata
import app.licenses.models  # noqa: F401
import app.settings.models  # noqa: F401
import app.services.models  # noqa: F401
import app.personnel.models  # noqa: F401
import app.changelog.models  # noqa: F401

# Create database tables
Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: additively sync the personnel schema BEFORE serving requests
    # (create_all adds new tables but not new columns to existing ones).
    ensure_personnel_schema(engine)
    # Startup: seed the service registry / migrate roles (idempotent)
    db = SessionLocal()
    try:
        seed_services(db)
        seed_changelog(db)
    finally:
        db.close()
    # Startup: launch background cleanup
    task = asyncio.create_task(cleanup_task())
    yield
    # Shutdown: cancel cleanup
    task.cancel()


app = FastAPI(
    title="Reconciliation Tool API",
    description="API for accounting data reconciliation",
    version="1.0.0",
    lifespan=lifespan
)

# CORS: read from env (production) or use dev defaults
cors_env = os.getenv("CORS_ORIGINS", "")
cors_origins = [o.strip() for o in cors_env.split(",") if o.strip()] if cors_env else [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(reconciliation_router)
app.include_router(licenses_router)
app.include_router(settings_router)
app.include_router(services_router)
app.include_router(personnel_router)
app.include_router(personnel_crud_router)
# f10104 хранит только справочник в файле — моделей и таблиц у модуля нет.
app.include_router(f10104_router)
# Курсы НБ РК — общий сервис, доступен любому аутентифицированному пользователю.
app.include_router(rates_router)
app.include_router(changelog_router)


@app.get("/")
async def root():
    return {"message": "Reconciliation Tool API", "version": "1.0.0"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
