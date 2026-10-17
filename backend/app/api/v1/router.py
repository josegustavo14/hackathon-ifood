from fastapi import APIRouter

from . import agent, cart, nutrition, recipes, shopping

router = APIRouter(prefix="/api/v1")
for module in (recipes, agent, nutrition, shopping, cart):
    router.include_router(module.router)
