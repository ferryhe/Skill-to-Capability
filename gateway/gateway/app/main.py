from fastapi import FastAPI

from .api.health import router as health_router

app = FastAPI(title="Skill Gateway")
app.include_router(health_router)
