"""Aggregates all v1 routers under a single /api/v1 prefix, mounted once in main.py."""

from fastapi import APIRouter

from app.api.v1 import auth, chat, graph, recommendations, resources, search

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(resources.router)
api_router.include_router(search.router)
api_router.include_router(chat.router)
api_router.include_router(graph.router)
api_router.include_router(recommendations.router)
