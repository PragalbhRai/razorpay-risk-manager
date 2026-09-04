from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.transactions import router as transactions_router
from app.api.alerts import router as alerts_router
from app.api.dashboard import router as dashboard_router

app = FastAPI(
    title="Razorpay Risk Manager",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(transactions_router)
app.include_router(alerts_router)
app.include_router(dashboard_router)

@app.get("/health")
def health_check():
    return {"status": "ok"}