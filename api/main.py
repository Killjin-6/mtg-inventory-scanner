from fastapi import FastAPI

from api.routes_phone import router as phone_router

app = FastAPI(title="MTG Scanner API")
app.include_router(phone_router)
