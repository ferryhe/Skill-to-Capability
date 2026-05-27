from fastapi import FastAPI

from .api.capabilities import router as capabilities_router
from .api.health import router as health_router

app = FastAPI(title="Skill Gateway")
app.include_router(health_router)
app.include_router(capabilities_router)
