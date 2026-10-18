from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.mocks.services import mock_proposal
from app.models.ingredient import Ingredient
from app.models.product import ProductCandidate
from app.models.recipe import Recipe
from app.shopping.catalog import catalog_ingredient_name
from app.shopping.engine import DeterministicShoppingEngine, base_quantity, optimize_packages
from app.shopping.models import (
    CulinaryConversion, ShoppingIngredient, ShoppingPlanRequest, ShoppingRecipe,
    ShoppingUnit, StockIngredient,
)


def ingredient(name="Muçarela", quantity="500", unit="g", **kwargs):
    return ShoppingIngredient(id=kwargs.pop("id", "cheese"), name=name, quantity=quantity, unit=unit, **kwargs)


def product(id, quantity, price, *, name=None, unit="g", merchant="market", available=True, **kwargs):
    return ProductCandidate(id=id, merchant_id=merchant, name=name or f"Muçarela {quantity} {unit}",
        price=price, package_quantity=quantity, package_unit=unit, available=available, source="test", **kwargs)


def plan(ingredients=None, products=None, stock=None, *, recipes=None, **kwargs):
    if recipes is None:
        recipes = [ShoppingRecipe(id="recipe", servings=4, target_servings=4,
            ingredients=ingredients if ingredients is not None else [ingredient()])]
    request = ShoppingPlanRequest(recipes=recipes, products=products or [], stock=stock or [], **kwargs)
    return DeterministicShoppingEngine().plan(request)


def test_metric_conversions_and_portion_scaling():
    assert base_quantity(Decimal("1.5"), ShoppingUnit.kg, "X", {}) == (Decimal("1500"), ShoppingUnit.g)
    assert base_quantity(Decimal("0.75"), ShoppingUnit.l, "X", {}) == (Decimal("750.00"), ShoppingUnit.ml)
    assert base_quantity(Decimal("250"), ShoppingUnit.ml, "X", {}) == (Decimal("250"), ShoppingUnit.ml)
    recipe = ShoppingRecipe(id="r", servings=2, target_servings=4,
        ingredients=[ingredient(quantity="0.3", unit="kg")])
    result = plan(recipes=[recipe], products=[product("a", "600", "20")])
    assert result.items[0].required_quantity == Decimal("600")
    assert result.items[0].unit == ShoppingUnit.g


def test_culinary_conversion_requires_ingredient_specific_source():
    without = plan(ingredients=[ingredient(name="Farinha", quantity="2", unit="xícara", id="flour")])
    assert without.items[0].reason == "conversion_not_verified"
    assert without.items[0].required_quantity is None
    rule = CulinaryConversion(ingredient_name="Farinha", from_unit="xícara", to_unit="g",
        amount_per_unit="120", source="medida conferida para esta farinha")
    result = plan(ingredients=[ingredient(name="Farinha", quantity="2", unit="xícara", id="flour")],
        conversions=[rule], products=[product("flour-250", "250", "8", name="Farinha 250 g")])
    assert result.items[0].required_quantity == Decimal("240")
    assert result.items[0].status == "matched"
    with pytest.raises(ValidationError):
        CulinaryConversion(ingredient_name="Farinha", from_unit="cup", to_unit="g", amount_per_unit="120", source="")


def test_consolidation_stock_partial_and_full():
    recipes = [
        ShoppingRecipe(id="r1", servings=4, target_servings=4, ingredients=[ingredient(quantity="300", id="a")]),
        ShoppingRecipe(id="r2", servings=4, target_servings=4, ingredients=[ingredient(quantity="0.4", unit="kg", id="b")]),
    ]
    result = plan(recipes=recipes, stock=[StockIngredient(name="Mussarela", quantity="200", unit="g")],
        aliases={"Mussarela": "Muçarela"}, products=[product("c", "500", "28")])
    line = result.items[0]
    assert line.ingredient_ids == ["a", "b"]
    assert line.required_quantity == Decimal("700")
    assert line.stock_used_quantity == Decimal("200")
    assert line.net_quantity == Decimal("500")
    assert line.selections[0].packages == 1
    full = plan(ingredients=[ingredient(name="Farinha", quantity="300", id="flour")],
        stock=[StockIngredient(name="Farinha", quantity="500", unit="g")])
    assert full.items[0].stock_quantity == Decimal("500")
    assert full.items[0].net_quantity == 0
    assert full.items[0].selections == []
    assert full.estimated_subtotal == 0
    assert full.merchant_id is None
    assert full.delivery_fee is None


def test_explicit_alias_matches_catalog_name():
    result = plan(ingredients=[ingredient(name="Mussarela")], aliases={"Mussarela": "Muçarela"},
        products=[product("a", "500", "20")])
    assert result.items[0].status == "matched"


def test_catalog_descriptors_can_follow_an_exact_ingredient_name():
    sauce = plan(ingredients=[ingredient(name="Molho de Tomate", quantity="500", id="sauce")],
                 products=[product("sauce-300", "300", "4", name="Molho de Tomate Tradicional 300g")])
    assert sauce.items[0].status == "matched"
    assert sauce.items[0].selections[0].packages == 2
    cheese = plan(products=[product("cheese-500", "500", "20", name="Queijo Muçarela 500g")])
    assert cheese.items[0].status == "matched"
    fresh_tomato = plan(ingredients=[ingredient(name="Tomate", quantity="500", id="tomato")],
                        products=[product("sauce-500", "500", "5", name="Molho de Tomate 500g")])
    assert fresh_tomato.items[0].status == "unavailable"


@pytest.mark.parametrize(("name", "expected"), [
    ("Abobrinha fatiada", "Abobrinha"),
    ("Cenoura, picada", "Cenoura"),
    ("Cebola cortada em cubos", "Cebola"),
    ("Brócolis em fatias finas", "Brócolis"),
    ("Tomate cereja picado", "Tomate cereja"),
    ("Tomate seco", "Tomate seco"),
    ("Molho de tomate picado", "Molho de tomate picado"),
    ("Carne moída", "Carne moída"),
    ("Queijo ralado", "Queijo ralado"),
])
def test_catalog_term_only_removes_produce_preparation(name, expected):
    assert catalog_ingredient_name(name) == expected


def test_legacy_match_uses_catalog_term_but_preserves_recipe_ingredient():
    sample = Recipe(id="vegetable", name="Legumes", servings=1, ingredients=[
        Ingredient(id="zucchini", name="Abobrinha fatiada", quantity="500", unit="g")
    ], instructions=[], source="test")
    engine = DeterministicShoppingEngine()
    shopping = engine.calculate(sample, 1)
    matched = engine.match_products(shopping, [product("zucchini-1", "500", "8", name="Abobrinha italiana 500g")])
    assert matched.items[0].status == "matched"
    assert matched.items[0].ingredient.name == "Abobrinha fatiada"
    assert matched.items[0].selected_product.name == "Abobrinha italiana 500g"


def test_incompatible_ingredients_do_not_consolidate():
    result = plan(ingredients=[ingredient(name="Leite", quantity="500", unit="ml", id="liquid"),
        ingredient(name="Leite", quantity="500", unit="g", id="solid")])
    assert len(result.items) == 2
    assert {item.unit for item in result.items} == {ShoppingUnit.ml, ShoppingUnit.g}


def test_mixed_packages_beat_two_b_packs_on_price():
    result = plan(products=[product("a", "200", "9"), product("b", "300", "13"), product("c", "500", "28")])
    line = result.items[0]
    assert [(selection.product.id, selection.packages) for selection in line.selections] == [("a", 1), ("b", 1)]
    assert line.bought_quantity == Decimal("500")
    assert line.excess_quantity == 0
    assert line.total_price == Decimal("22")
    assert line.optimal is True


def test_tie_breaks_waste_then_package_count_then_id():
    waste = plan(products=[product("a", "500", "20"), product("b", "300", "10")])
    assert [s.product.id for s in waste.items[0].selections] == ["a"]
    count = plan(products=[product("a", "250", "10"), product("b", "500", "20")])
    assert [s.product.id for s in count.items[0].selections] == ["b"]
    tied = [product("z", "500", "20"), product("a", "500", "20")]
    assert [s.product.id for s in plan(products=tied).items[0].selections] == ["a"]
    assert plan(products=list(reversed(tied))).model_dump() == plan(products=tied).model_dump()


def test_unavailable_incompatible_restrictions_and_authorized_substitution():
    unavailable = plan(products=[product("a", "500", "10", available=False)])
    assert unavailable.items[0].status == "unavailable"
    incompatible = plan(products=[product("a", "500", "10", name="Farinha 500 g")])
    assert incompatible.items[0].status == "unavailable"
    dietary = plan(ingredients=[ingredient(required_tags=["sem lactose"])],
        products=[product("a", "500", "10")])
    assert dietary.items[0].status == "unavailable"
    authorized = plan(ingredients=[ingredient(authorized_product_ids=["a"], required_tags=["sem lactose"])],
        products=[product("a", "500", "10", name="Queijo vegetal 500 g", tags=["sem lactose"])])
    assert authorized.items[0].status == "matched"
    cross_category = plan(ingredients=[ingredient(category="laticínios", authorized_product_ids=["a"])],
        products=[product("a", "500", "10", name="Queijo vegetal 500 g", category="vegetal")])
    assert cross_category.items[0].status == "matched"
    unsafe_stock = plan(ingredients=[ingredient(required_tags=["sem lactose"])],
        stock=[StockIngredient(name="Muçarela", quantity="500", unit="g")],
        products=[product("safe", "500", "10", tags=["sem lactose"])])
    assert unsafe_stock.items[0].net_quantity == Decimal("500")
    safe_stock = plan(ingredients=[ingredient(required_tags=["sem lactose"])],
        stock=[StockIngredient(name="Muçarela", quantity="500", unit="g", tags=["sem lactose"])])
    assert safe_stock.items[0].net_quantity == 0


def test_unknown_quantities_empty_catalog_and_invalid_values():
    result = plan(ingredients=[ingredient(quantity=None)])
    assert result.items[0].reason == "unknown_quantity"
    assert result.items[0].net_quantity is None
    assert result.unresolved_ingredients == ["cheese"]
    assert plan().items[0].status == "unavailable"
    with pytest.raises(ValidationError):
        ShoppingPlanRequest(recipes=[])
    with pytest.raises(ValidationError):
        ingredient(quantity="-1")
    with pytest.raises(ValidationError):
        product("bad", "500", "-1")
    with pytest.raises(ValidationError):
        ShoppingPlanRequest(recipes=[ShoppingRecipe(id="r", servings=1, target_servings=1, ingredients=[])],
            products=[product("a", "500", "10"), product("a", "300", "8")])


def test_merchant_isolation_known_fee_and_fallback():
    result = plan(products=[product("expensive", "500", "12", merchant="one"),
        product("cheap", "500", "10", merchant="two")], delivery_fees={"one": "0", "two": "5"})
    assert result.merchant_id == "one"
    assert result.estimated_subtotal == Decimal("12")
    assert result.estimated_total == Decimal("12")
    limited = plan(ingredients=[ingredient(quantity="100001")],
        products=[product("one", "1", "0.01"), product("two", "2", "0.02")])
    assert limited.items[0].status == "matched"
    assert limited.optimal is False
    assert "not_proven_optimal" in limited.items[0].reason
    unknown_fee = plan(products=[product("one", "500", "12", merchant="one"),
        product("two", "500", "10", merchant="two")], delivery_fees={"one": "0"})
    assert unknown_fee.merchant_id == "two"
    assert unknown_fee.estimated_total is None
    assert unknown_fee.optimal is False
    assert any("Frete desconhecido" in warning for warning in unknown_fee.warnings)


def test_endpoint_accepts_structured_input_without_gateway():
    client = TestClient(app)
    body = {"recipes": [{"id": "r", "servings": 4, "target_servings": 4,
        "ingredients": [{"id": "cheese", "name": "Muçarela", "quantity": "500", "unit": "g"}]}],
        "products": [product("a", "200", "9").model_dump(mode="json"),
            product("b", "300", "13").model_dump(mode="json")]}
    response = client.post("/api/v1/shopping/plan", json=body)
    assert response.status_code == 200
    assert response.json()["estimated_subtotal"] == "22.00"
    assert len(response.json()["items"][0]["selections"]) == 2
    assert client.post("/api/v1/shopping/plan", json={"recipes": []}).status_code == 422


def test_legacy_shopping_list_and_cart_preserve_mixed_selection():
    recipe = Recipe(id="r", name="Teste", servings=1, source="test", instructions=[],
        ingredients=[Ingredient(id="cheese", name="Muçarela", quantity="500", unit="g")])
    engine = DeterministicShoppingEngine()
    pending = engine.calculate(recipe, 1)
    matched = engine.match_products(pending, [product("a", "200", "9"), product("b", "300", "13")])
    assert matched.estimated_subtotal == Decimal("22")
    assert len(matched.items) == 2
    proposal = mock_proposal(matched)
    assert len(proposal.items) == 2
    assert proposal.estimated_subtotal == Decimal("22")
    rematched = engine.match_products(matched, [product("a", "200", "9"), product("b", "300", "13")])
    assert rematched.estimated_subtotal == Decimal("22")
    assert len(rematched.items) == 2


def test_legacy_match_consolidates_duplicate_ingredient_names():
    recipe = Recipe(id="r", name="Teste", servings=1, source="test", instructions=[],
        ingredients=[Ingredient(id="first", name="Muçarela", quantity="200", unit="g"),
            Ingredient(id="second", name="Muçarela", quantity="300", unit="g")])
    engine = DeterministicShoppingEngine()
    matched = engine.match_products(engine.calculate(recipe, 1), [product("a", "500", "20")])
    assert len(matched.items) == 1
    assert matched.items[0].ingredient.quantity == Decimal("500")
    assert matched.estimated_subtotal == Decimal("20")


def test_optional_ingredients_are_excluded_by_default():
    optional = ingredient(name="Muçarela", quantity="100", optional=True)
    without = plan(ingredients=[optional])
    with_optional = plan(ingredients=[optional], include_optional=True)
    assert without.items == []
    assert with_optional.items[0].required_quantity == Decimal("100")
