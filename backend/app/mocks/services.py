from decimal import Decimal, ROUND_CEILING

from app.models.cart import CartProposal
from app.models.nutrition import NutritionCalculation, NutritionFacts, NutritionStatus, UnresolvedIngredient
from app.models.product import ProductCandidate
from app.models.recipe import Recipe
from app.models.shopping import ShoppingItem, ShoppingItemStatus, ShoppingList, ShoppingListStatus
from app.integrations.ifood.models import (
    AddressListResponse, AvailabilityStatus, ItemDetailsResult, MCPToolResult,
    MerchantDetailsResult, MerchantType,
)
from app.integrations.ifood.cart import CheckoutResult
from .data import load_json, nutrition_total, products, recipe


class MockRecipeProvider:
    async def search(self, query: str) -> list[Recipe]:
        sample = recipe()
        return [sample] if query.casefold() in sample.name.casefold() or "lasanha" in query.casefold() else []

    async def get_by_id(self, recipe_id: str) -> Recipe | None:
        sample = recipe()
        pasta = load_json("pasta.json")
        if recipe_id == pasta["id"]:
            return Recipe.model_validate(pasta)
        return sample if recipe_id == sample.id else None


class MockIFoodGateway:
    async def list_tools(self) -> list[dict]:
        return []

    async def list_addresses(self) -> AddressListResponse:
        return AddressListResponse(addresses=[], agent_hints={"noResultsGuidance": "No saved addresses found."})

    async def search_offers(self, query: str, **kwargs) -> MCPToolResult:
        matches = await self.search_products(query, kwargs.get("merchant_id"))
        return MCPToolResult(
            tool="mock_searchOffers",
            data={"items": [item.model_dump(mode="json") for item in matches]},
        )

    async def browse_offers(self, **kwargs) -> MCPToolResult:
        return MCPToolResult(
            tool="mock_browseOffers",
            data={"merchantType": str(kwargs.get("merchant_type", MerchantType.GROCERIES)), "items": []},
        )

    async def search_products(self, query: str, merchant_id: str | None = None, **kwargs) -> list[ProductCandidate]:
        return [p for p in products() if query.casefold() in p.name.casefold() and (merchant_id is None or p.merchant_id == merchant_id)]

    async def get_item(self, item_id: str, merchant_id: str, **kwargs) -> ItemDetailsResult:
        item = next((product for product in products() if product.id == item_id), None)
        return ItemDetailsResult(
            tool="mock_getItem", data=item.model_dump(mode="json") if item else {},
            item_id=item_id, merchant_id=item.merchant_id if item else merchant_id,
            name=item.name if item else None, price=item.price if item else None,
            unit_price=item.price if item else None,
            availability=(AvailabilityStatus.available if item and item.available else
                          AvailabilityStatus.unavailable if item else AvailabilityStatus.unknown),
        )

    async def get_merchant(self, merchant_id: str, **kwargs) -> MerchantDetailsResult:
        return MerchantDetailsResult(tool="mock_getMerchant", data={}, merchant_id=merchant_id)

    async def select_pix_payment(self, cart_id: str, merchant_id: str | None = None) -> bool:
        return False

    async def submit_order(self, cart_id: str, *, confirmed: bool, document: str | None = None) -> CheckoutResult:
        raise RuntimeError("Mock mode never submits an iFood order")


class MockNutritionProvider:
    async def calculate(self, recipe: Recipe, servings: int, include_optional: bool = False) -> NutritionCalculation:
        if recipe.id != load_json("nutrition.json")["recipe_id"]:
            return NutritionCalculation(
                recipe_id=recipe.id, servings=servings, status=NutritionStatus.incomplete,
                total=None, per_serving=None,
                unresolved_ingredients=[UnresolvedIngredient(ingredient_id=i.id, name=i.name, reason="source_record_unavailable") for i in recipe.ingredients],
                warnings=["O mock nutricional cobre apenas a receita demonstrativa da EP00."],
            )
        total = nutrition_total()
        factor = Decimal(servings) / recipe.servings
        scaled_total = NutritionFacts(
            calories_kcal=total.calories_kcal * factor,
            protein_g=total.protein_g * factor,
            carbohydrates_g=total.carbohydrates_g * factor,
            fat_g=total.fat_g * factor,
            reference_quantity="1", reference_unit="recipe", basis="recipe_total",
            source=total.source, estimated=True,
        )
        per_serving = NutritionFacts(
            calories_kcal=scaled_total.calories_kcal / servings,
            protein_g=scaled_total.protein_g / servings,
            carbohydrates_g=scaled_total.carbohydrates_g / servings,
            fat_g=scaled_total.fat_g / servings,
            reference_quantity="1", reference_unit="serving", basis="per_serving",
            source=total.source, estimated=True,
        )
        return NutritionCalculation(
            recipe_id=recipe.id, servings=servings, status=NutritionStatus.complete,
            total=scaled_total, per_serving=per_serving,
            warnings=["Valores demonstrativos do mock EP00."],
        )


class MockShoppingEngine:
    def calculate(self, recipe: Recipe, servings: int) -> ShoppingList:
        scaled = [ingredient.model_copy(update={"quantity": ingredient.quantity * Decimal(servings) / recipe.servings}) for ingredient in recipe.ingredients]
        return ShoppingList(
            id=f"shopping-{recipe.id}-{servings}", recipe_id=recipe.id,
            items=[ShoppingItem(ingredient=i, purchase_quantity=0, total_price="0.00", status=ShoppingItemStatus.pending) for i in scaled],
            estimated_subtotal="0.00", unresolved_ingredients=scaled, status=ShoppingListStatus.pending,
        )

    def match_products(self, shopping_list: ShoppingList, products: list[ProductCandidate]) -> ShoppingList:
        by_id = {p.id: p for p in products}
        preferred = load_json("products.json")["preferred_product_by_ingredient"]
        items = []
        for item in shopping_list.items:
            ingredient = item.ingredient
            product = by_id.get(preferred.get(ingredient.id, ""))
            if product is None or not product.available or product.package_unit != ingredient.unit or product.package_quantity is None:
                items.append(item.model_copy(update={"selected_product": None, "purchase_quantity": 0, "total_price": Decimal("0.00"), "status": ShoppingItemStatus.unavailable}))
                continue
            count = int((ingredient.quantity / product.package_quantity).to_integral_value(rounding=ROUND_CEILING))
            items.append(item.model_copy(update={"selected_product": product, "purchase_quantity": count, "total_price": product.price * count, "status": ShoppingItemStatus.matched}))
        unresolved = [item.ingredient for item in items if item.status != ShoppingItemStatus.matched]
        return ShoppingList(
            id=shopping_list.id, recipe_id=shopping_list.recipe_id, items=items,
            estimated_subtotal=sum((item.total_price for item in items), start=Decimal("0.00")),
            unresolved_ingredients=unresolved,
            status=ShoppingListStatus.needs_review if unresolved else ShoppingListStatus.ready_for_review,
        )


def mock_proposal(shopping_list: ShoppingList) -> CartProposal:
    template = load_json("cart.json")
    items = [item for item in shopping_list.items if item.selected_product and item.purchase_quantity]
    merchant_ids = {item.selected_product.merchant_id for item in items}
    return CartProposal(
        id=f"{template['id_prefix']}{shopping_list.id}",
        merchant_id=next(iter(merchant_ids)) if len(merchant_ids) == 1 else None,
        items=items,
        estimated_subtotal=sum((item.total_price for item in items), start=Decimal("0.00")),
        currency=template["currency"],
        requires_confirmation=template["requires_confirmation"],
        status=template["ready_status"] if items else template["empty_status"],
    )
