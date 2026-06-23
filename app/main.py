from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes
from app.core import logging as logmod


@asynccontextmanager
async def lifespan(_: FastAPI):
    logmod.logger.info("Starting Multimodal RAG backend")
    yield
    logmod.logger.info("Stopping Multimodal RAG backend")


app = FastAPI(title="Multimodal RAG Chatbot", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(routes.router)


@app.get("/")
def root():
    return {
        "message": "Multimodal RAG backend is running",
        "docs": "http://127.0.0.1:8000/docs"
    }
