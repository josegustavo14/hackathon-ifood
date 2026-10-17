from enum import Enum
from typing import Any

from .cart import CartProposal
from .common import Contract
from .nutrition import NutritionFacts
from .recipe import Recipe
from .shopping import ShoppingList


class AgentStatus(str, Enum):
    completed = "completed"
    needs_input = "needs_input"
    error = "error"


class AgentRequest(Contract):
    message: str
    session_id: str | None = None
    context: dict[str, Any] | None = None


class AgentResponse(Contract):
    session_id: str
    message: str
    status: AgentStatus
    recipe: Recipe | None = None
    shopping_list: ShoppingList | None = None
    cart_proposal: CartProposal | None = None
    nutrition: NutritionFacts | None = None
