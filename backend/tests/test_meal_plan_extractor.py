import pytest

from app.agent.meal_plan_extractor import MealPlanParseError, parse


def test_parse_meal_plan_text_and_keep_alternatives_separate():
    plan = parse(
        """
        Segunda
        Café da manhã: 40 g aveia; 1 banana
        Alternativas: 1 banana ou 1 maçã
        Almoço: 100 g arroz; 120 g frango
        Terça | Jantar | 80 g macarrão; 100 g carne moída
        """,
        "plano.pdf",
    )

    assert plan.days == ["Segunda", "Terça"]
    assert len(plan.meals) == 3
    assert plan.meals[0].ingredients[0].name == "aveia"
    assert plan.meals[0].ingredients[0].unit == "g"
    assert len(plan.meals[0].alternative_groups) == 1
    assert len(plan.meals[0].alternative_groups[0].options) == 2


def test_parse_reports_ambiguous_ingredients_without_fabricating_quantity():
    plan = parse("Segunda\nJantar: sal a gosto; 100 g arroz", "plano.pdf")

    assert [ingredient.name for ingredient in plan.meals[0].ingredients] == ["arroz"]
    assert any("sal" in warning for warning in plan.extraction_warnings)


def test_parse_rejects_text_without_meals():
    with pytest.raises(MealPlanParseError):
        parse("Este PDF não contém um plano alimentar", "plano.pdf")
