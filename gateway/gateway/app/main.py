from fastapi import FastAPI

from .api.capabilities import router as capabilities_router
from .api.errors import register_error_handlers
from .api.health import router as health_router
from .api.tasks import router as tasks_router

app = FastAPI(title="Skill Gateway")
register_error_handlers(app)
app.include_router(health_router)
app.include_router(capabilities_router)
app.include_router(tasks_router)
