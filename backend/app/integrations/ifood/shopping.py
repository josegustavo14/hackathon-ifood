"""Product matching rules for live iFood candidates.

Search results are already scoped by ingredient by the caller. This layer only
checks stock and package compatibility before calculating the number of packs.
"""

from decimal import Decimal, ROUND_CEILING

from app.models.ingredient import Ingredient
from app.models.product import ProductCandidate
from app.models.recipe import Recipe
from app.models.shopping import ShoppingItem, ShoppingItemStatus, ShoppingList, ShoppingListStatus


class IFoodShoppingEngine:
    def calculate(self, recipe: Recipe, servings: int) -> ShoppingList:
        ingredients = [
            ingredient.model_copy(update={"quantity": ingredient.quantity * Decimal(servings) / recipe.servings})
            for ingredient in recipe.ingredients
        ]
        return ShoppingList(
            id=f"shopping-{recipe.id}-{servings}", recipe_id=recipe.id,
            items=[self._unmatched(ingredient, ShoppingItemStatus.pending) for ingredient in ingredients],
            estimated_subtotal="0.00", unresolved_ingredients=ingredients, status=ShoppingListStatus.pending,
        )

    def match_products(self, shopping_list: ShoppingList, products: list[ProductCandidate]) -> ShoppingList:
        items = [self._match(item.ingredient, products) for item in shopping_list.items]
        unresolved = [item.ingredient for item in items if item.status is not ShoppingItemStatus.matched]
        return ShoppingList(
            id=shopping_list.id, recipe_id=shopping_list.recipe_id, items=items,
            estimated_subtotal=sum((item.total_price for item in items), start=Decimal("0.00")),
            unresolved_ingredients=unresolved,
            status=ShoppingListStatus.needs_review if unresolved else ShoppingListStatus.ready_for_review,
        )

    def _match(self, ingredient: Ingredient, products: list[ProductCandidate]) -> ShoppingItem:
        available = [product for product in products if product.available]
        compatible = [
            product for product in available
            if product.package_quantity is not None and product.package_unit == ingredient.unit
        ]
        if compatible:
            product = min(compatible, key=lambda candidate: (candidate.price, candidate.id))
            count = int((ingredient.quantity / product.package_quantity).to_integral_value(rounding=ROUND_CEILING))
            return ShoppingItem(
                ingredient=ingredient, selected_product=product, purchase_quantity=count,
                total_price=product.price * count, status=ShoppingItemStatus.matched,
            )
        # A live result without a usable package size needs a human decision;
        # an out-of-stock result is explicitly reported as unavailable.
        status = ShoppingItemStatus.needs_review if available else ShoppingItemStatus.unavailable
        return self._unmatched(ingredient, status)

    @staticmethod
    def _unmatched(ingredient: Ingredient, status: ShoppingItemStatus) -> ShoppingItem:
        return ShoppingItem(
            ingredient=ingredient, selected_product=None, purchase_quantity=0,
            total_price="0.00", status=status,
        )
