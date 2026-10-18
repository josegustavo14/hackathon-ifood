"""Deterministic shopping calculations; no LLM or external service calls."""

import re
import unicodedata
from decimal import Decimal, ROUND_CEILING
from itertools import product as combinations

from app.models.ingredient import Ingredient, Unit
from app.models.product import ProductCandidate
from app.models.recipe import Recipe
from app.models.shopping import ShoppingItem, ShoppingItemStatus, ShoppingList, ShoppingListStatus

from .catalog import catalog_ingredient_name, catalog_search_terms
from .models import (
    CulinaryConversion, ProductSelection, ShoppingIngredient, ShoppingPlan,
    ShoppingPlanItem, ShoppingPlanRequest, ShoppingRecipe, ShoppingUnit,
)

MAX_EXACT_COMBINATIONS = 100_000
PACKAGE_SUFFIX = re.compile(r"\s+\d+(?:[.,]\d+)?\s*(?:kg|g|ml|l|unidades?|unit)$")


def normalize(value: str) -> str:
    plain = "".join(char for char in unicodedata.normalize("NFKD", value.casefold()) if not unicodedata.combining(char))
    return " ".join(plain.split())


def base_quantity(amount: Decimal, unit: ShoppingUnit, name: str, conversions: dict[tuple[str, ShoppingUnit], CulinaryConversion]) -> tuple[Decimal, ShoppingUnit] | None:
    if unit == ShoppingUnit.kg:
        return amount * 1000, ShoppingUnit.g
    if unit == ShoppingUnit.l:
        return amount * 1000, ShoppingUnit.ml
    if unit in {ShoppingUnit.g, ShoppingUnit.ml, ShoppingUnit.unit}:
        return amount, unit
    rule = conversions.get((normalize(name), unit))
    if rule is None:
        return None
    return amount * rule.amount_per_unit, rule.to_unit


def product_quantity(product: ProductCandidate) -> tuple[Decimal, ShoppingUnit] | None:
    if product.package_quantity is None or product.package_unit is None:
        return None
    return base_quantity(product.package_quantity, ShoppingUnit(product.package_unit.value), product.name, {})


def product_name_matches(item: ShoppingPlanItem, product: ProductCandidate, required_tags: frozenset[str],
                         authorized_ids: frozenset[str], canonical_name: str) -> bool:
    if not required_tags.issubset({normalize(tag) for tag in product.tags}):
        return False
    if product.id in authorized_ids:
        return True
    if item.category is not None and normalize(product.category or "") != normalize(item.category):
        return False
    canonical_product = PACKAGE_SUFFIX.sub("", normalize(product.name)).strip()
    if canonical_product == canonical_name or canonical_product.startswith(canonical_name + " "):
        return True
    # Catalog names often include the broad product type before the ingredient.
    # This narrow, explicit form admits "Queijo Muçarela" for "muçarela"
    # without treating "Molho de Tomate" as a fresh "tomate".
    return canonical_product == "queijo " + canonical_name or canonical_product.startswith("queijo " + canonical_name + " ")


def matches_product(item: ShoppingPlanItem, product: ProductCandidate, required_tags: frozenset[str],
                    authorized_ids: frozenset[str], canonical_name: str) -> bool:
    size = product_quantity(product)
    return (product.available and size is not None and size[1] == item.unit
            and product_name_matches(item, product, required_tags, authorized_ids, canonical_name))


def ceil_packages(required: Decimal, size: Decimal) -> int:
    return int((required / size).to_integral_value(rounding=ROUND_CEILING))


def optimize_packages(required: Decimal, candidates: list[ProductCandidate]) -> tuple[list[ProductSelection], Decimal, Decimal, bool]:
    """Find the lexicographic optimum, or a marked deterministic fallback."""
    ordered = sorted(candidates, key=lambda item: item.id)
    sizes = [product_quantity(item)[0] for item in ordered]
    bounds = [ceil_packages(required, size) for size in sizes]
    state_count = 1
    for bound in bounds:
        state_count *= bound + 1
        if state_count > MAX_EXACT_COMBINATIONS:
            break
    exact = len(ordered) == 1 or (len(ordered) <= 8 and state_count <= MAX_EXACT_COMBINATIONS)
    if exact:
        vectors = ([bounds[0]],) if len(ordered) == 1 else combinations(*(range(bound + 1) for bound in bounds))
    else:
        vectors = ([ceil_packages(required, size) if index == chosen else 0 for index in range(len(ordered))] for chosen, size in enumerate(sizes))
    best_key = None
    best_counts = None
    best_bought = Decimal(0)
    best_cost = Decimal(0)
    for counts in vectors:
        bought = sum((size * count for size, count in zip(sizes, counts)), Decimal(0))
        if bought < required:
            continue
        cost = sum((item.price * count for item, count in zip(ordered, counts)), Decimal(0))
        identifiers = tuple((item.id, count) for item, count in zip(ordered, counts) if count)
        key = (cost, bought - required, sum(counts), identifiers)
        if best_key is None or key < best_key:
            best_key, best_counts, best_bought, best_cost = key, counts, bought, cost
    assert best_counts is not None  # each candidate's single-product cover is valid
    selected = [
        ProductSelection(product=item, packages=count, bought_quantity=size * count, total_price=item.price * count)
        for item, size, count in zip(ordered, sizes, best_counts) if count
    ]
    return selected, best_bought, best_cost, exact


class DeterministicShoppingEngine:
    def plan(self, request: ShoppingPlanRequest) -> ShoppingPlan:
        aliases = {normalize(key): normalize(value) for key, value in request.aliases.items()}
        conversions: dict[tuple[str, ShoppingUnit], CulinaryConversion] = {}
        for rule in request.conversions:
            name = normalize(rule.ingredient_name)
            key = (aliases.get(name, name), rule.from_unit)
            if key in conversions and conversions[key] != rule:
                raise ValueError(f"conflicting conversion for {rule.ingredient_name} {rule.from_unit}")
            conversions[key] = rule

        groups: dict[tuple, dict] = {}
        unresolved: list[ShoppingPlanItem] = []
        for recipe in request.recipes:
            for ingredient in recipe.ingredients:
                if ingredient.optional and not request.include_optional:
                    continue
                canonical = aliases.get(normalize(ingredient.name), normalize(ingredient.name))
                if ingredient.quantity is None:
                    unresolved.append(ShoppingPlanItem(ingredient_ids=[ingredient.id], name=ingredient.name, category=ingredient.category,
                        unit=ingredient.unit, status=ShoppingItemStatus.needs_review, reason="unknown_quantity", optimal=False))
                    continue
                scaled = ingredient.quantity * Decimal(recipe.target_servings) / recipe.servings
                converted = base_quantity(scaled, ingredient.unit, canonical, conversions)
                if converted is None:
                    unresolved.append(ShoppingPlanItem(ingredient_ids=[ingredient.id], name=ingredient.name, category=ingredient.category,
                        status=ShoppingItemStatus.needs_review, reason="conversion_not_verified", optimal=False))
                    continue
                amount, unit = converted
                tags = frozenset(map(normalize, ingredient.required_tags))
                authorized = frozenset(ingredient.authorized_product_ids)
                key = (canonical, normalize(ingredient.category or ""), unit, tags, authorized)
                if key not in groups:
                    groups[key] = {"name": ingredient.name, "category": ingredient.category, "unit": unit,
                        "required": Decimal(0), "ids": [], "tags": tags, "authorized": authorized}
                groups[key]["required"] += amount
                groups[key]["ids"].append(ingredient.id)

        stocks: list[dict] = []
        warnings: list[str] = []
        for stock in request.stock:
            canonical = aliases.get(normalize(stock.name), normalize(stock.name))
            converted = base_quantity(stock.quantity, stock.unit, canonical, conversions)
            if converted is None:
                warnings.append(f"Estoque ignorado por conversão não verificada: {stock.name}")
                continue
            amount, unit = converted
            stocks.append({"key": (canonical, normalize(stock.category or ""), unit),
                "tags": frozenset(map(normalize, stock.tags)), "remaining": amount})

        allocations: dict[tuple, tuple[Decimal, Decimal]] = {}
        for key in sorted(groups, key=lambda value: (-len(value[3]), value[0], value[1], value[2].value)):
            group = groups[key]
            eligible = [stock for stock in stocks if stock["key"] == key[:3] and key[3].issubset(stock["tags"])]
            available = sum((stock["remaining"] for stock in eligible), Decimal(0))
            needed = group["required"]
            for stock in eligible:
                used = min(stock["remaining"], needed)
                stock["remaining"] -= used
                needed -= used
                if needed == 0:
                    break
            allocations[key] = (available, group["required"] - needed)

        prepared: list[tuple[ShoppingPlanItem, frozenset[str], frozenset[str], str]] = []
        for key, group in groups.items():
            available, used = allocations[key]
            net = group["required"] - used
            item = ShoppingPlanItem(ingredient_ids=group["ids"], name=group["name"], category=group["category"],
                unit=group["unit"], required_quantity=group["required"], stock_quantity=available, stock_used_quantity=used,
                net_quantity=net, bought_quantity=Decimal(0) if net == 0 else None,
                excess_quantity=Decimal(0) if net == 0 else None,
                status=ShoppingItemStatus.matched if net == 0 else ShoppingItemStatus.pending,
                reason="covered_by_stock" if net == 0 else "awaiting_product_match")
            prepared.append((item, group["tags"], group["authorized"], key[0]))

        merchants = [request.merchant_id] if request.merchant_id is not None else sorted({p.merchant_id for p in request.products})
        if not merchants:
            merchants = [None]
        compare_delivery = all(merchant in request.delivery_fees for merchant in merchants if merchant is not None)
        best = None
        best_key = None
        for merchant in merchants:
            items = list(unresolved)
            merchant_products = [p for p in request.products if p.merchant_id == merchant]
            for item, tags, authorized, canonical_name in prepared:
                if item.net_quantity == 0:
                    items.append(item)
                    continue
                compatible = [p for p in merchant_products if matches_product(item, p, tags, authorized, canonical_name)]
                if not compatible:
                    items.append(item.model_copy(update={"status": ShoppingItemStatus.unavailable, "reason": "no_compatible_available_product", "optimal": False}))
                    continue
                selections, bought, cost, exact = optimize_packages(item.net_quantity, compatible)
                items.append(item.model_copy(update={"selections": selections, "bought_quantity": bought,
                    "excess_quantity": bought - item.net_quantity, "total_price": cost, "status": ShoppingItemStatus.matched,
                    "reason": "lowest_cost_then_waste_then_packages" if exact else "deterministic_fallback_not_proven_optimal", "optimal": exact}))
            subtotal = sum((item.total_price for item in items), Decimal("0.00"))
            unresolved_ids = [identifier for item in items if item.status != ShoppingItemStatus.matched for identifier in item.ingredient_ids]
            has_purchase = any(item.selections for item in items)
            fee = request.delivery_fees.get(merchant) if merchant is not None and has_purchase else None
            total = subtotal + fee if fee is not None else None
            excess = sum((item.excess_quantity or Decimal(0) for item in items), Decimal(0))
            packages = sum(selection.packages for item in items for selection in item.selections)
            key = (len(unresolved_ids), total if compare_delivery and total is not None else subtotal,
                excess, packages, merchant or "")
            if best_key is None or key < best_key:
                best_key = key
                best = (items, subtotal, fee, total, merchant if has_purchase else None, unresolved_ids)
        items, subtotal, fee, total, merchant, unresolved_ids = best
        has_purchase = any(item.selections for item in items)
        if has_purchase and not compare_delivery:
            warnings.append("Frete desconhecido para algum estabelecimento; a comparação considera apenas preços dos produtos.")
        if any(not item.optimal and item.status == ShoppingItemStatus.matched for item in items):
            warnings.append("Busca limitada: uma ou mais escolhas de embalagens não têm ótimo comprovado.")
        return ShoppingPlan(items=items, estimated_subtotal=subtotal, delivery_fee=fee, estimated_total=total,
            merchant_id=merchant, unresolved_ingredients=unresolved_ids,
            status=ShoppingListStatus.needs_review if unresolved_ids else
                (ShoppingListStatus.pending if not items else ShoppingListStatus.ready_for_review),
            optimal=not unresolved_ids and all(item.optimal for item in items)
                and (not has_purchase or compare_delivery or len(merchants) == 1), warnings=warnings)

    def calculate(self, recipe: Recipe, servings: int) -> ShoppingList:
        if servings <= 0:
            raise ValueError("servings must be positive")
        scaled = [ingredient.model_copy(update={"quantity": ingredient.quantity * Decimal(servings) / recipe.servings}) for ingredient in recipe.ingredients]
        return ShoppingList(id=f"shopping-{recipe.id}-{servings}", recipe_id=recipe.id,
            items=[ShoppingItem(ingredient=i, purchase_quantity=0, total_price="0.00", status=ShoppingItemStatus.pending) for i in scaled],
            estimated_subtotal="0.00", unresolved_ingredients=scaled, status=ShoppingListStatus.pending)

    def match_products(self, shopping_list: ShoppingList, products: list[ProductCandidate]) -> ShoppingList:
        ingredient_by_id: dict[str, Ingredient] = {}
        for item in shopping_list.items:
            previous = ingredient_by_id.get(item.ingredient.id)
            if previous is not None and previous != item.ingredient:
                raise ValueError(f"conflicting ingredient id: {item.ingredient.id}")
            ingredient_by_id[item.ingredient.id] = item.ingredient
        recipe = ShoppingRecipe(id=shopping_list.recipe_id or shopping_list.id, servings=1, target_servings=1,
            ingredients=[ShoppingIngredient(id=ingredient.id, name=catalog_ingredient_name(ingredient.name),
                quantity=ingredient.quantity, unit=ingredient.unit.value) for ingredient in ingredient_by_id.values()])
        plan = self.plan(ShoppingPlanRequest(recipes=[recipe], products=products))
        items: list[ShoppingItem] = []
        for result in plan.items:
            ingredient = ingredient_by_id[result.ingredient_ids[0]]
            if result.required_quantity is not None and result.unit is not None:
                ingredient = ingredient.model_copy(update={"quantity": result.required_quantity, "unit": Unit(result.unit.value)})
            if result.selections:
                for selected in result.selections:
                    items.append(ShoppingItem(ingredient=ingredient, selected_product=selected.product,
                        purchase_quantity=selected.packages, total_price=selected.total_price,
                        status=ShoppingItemStatus.matched, reason=result.reason))
            else:
                status, reason = result.status, result.reason
                terms = catalog_search_terms(ingredient.name)
                suggestions = sorted((product for product in products
                    if product.available and any(product_name_matches(result, product, frozenset(), frozenset(), normalize(term))
                            for term in terms)), key=lambda product: (product.price, product.merchant_id, product.id))[:20]
                if " ou " in normalize(ingredient.name):
                    status, reason = ShoppingItemStatus.needs_review, "choose_alternative"
                elif status == ShoppingItemStatus.unavailable:
                    if suggestions:
                        status = ShoppingItemStatus.needs_review
                        reason = ("package_quantity_unknown" if any(product_quantity(product) is None for product in suggestions)
                                  else "unit_conversion_not_verified")
                items.append(ShoppingItem(ingredient=ingredient, purchase_quantity=0, total_price="0.00",
                                          status=status, reason=reason, suggested_products=suggestions))
        unresolved = [item.ingredient for item in items if item.status != ShoppingItemStatus.matched]
        return ShoppingList(id=shopping_list.id, recipe_id=shopping_list.recipe_id, items=items,
            estimated_subtotal=plan.estimated_subtotal, unresolved_ingredients=unresolved,
            status=ShoppingListStatus.needs_review if unresolved else ShoppingListStatus.ready_for_review)
