from fastapi import APIRouter

from . import agent, cart, ifood, ifood_auth, nutrition, recipes, shopping

router = APIRouter(prefix="/api/v1")
for module in (recipes, agent, nutrition, shopping, cart, ifood_auth, ifood):
    router.include_router(module.router)
