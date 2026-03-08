from fastapi import Depends, FastAPI

from api.auth import require_app_auth
from api.routes_inventory import router as inventory_router
from api.routes_phone import router as phone_router

app = FastAPI(title="MTG Scanner API")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(phone_router, dependencies=[Depends(require_app_auth)])
app.include_router(inventory_router, dependencies=[Depends(require_app_auth)])
