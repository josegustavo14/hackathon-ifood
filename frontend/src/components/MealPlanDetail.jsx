import React from 'react'
import Icon from './Icon'
import NutritionPanel from './NutritionPanel'
import { amount, planIngredients, quantity } from '../utils'

export default function MealPlanDetail({ plan, pantry, busy, onPantry, onBuild }) {
  const ingredients = planIngredients(plan)
  return (
    <>
      <p className="subtle small-text">Arquivo: {plan.source_filename}</p>
      {plan.extraction_warnings?.map((warning, index) => (
        <div className="alert info" key={index}>
          {warning}
        </div>
      ))}
      {plan.nutrition && <NutritionPanel calculation={plan.nutrition} />}
      <div className="detail-grid">
        <div>
          <div className="ingredient-heading">
            <h3>Lista de compras</h3>
            <span className="pill">{ingredients.length} itens</span>
          </div>
          <p className="subtle small-text">
            Quantidades somadas de todas as refeições do plano, já considerando a frequência de cada uma. Marque “já
            tenho” para retirar um ingrediente da compra.
          </p>
          <ul className="ingredient-list">
            {ingredients.map(item => (
              <li key={item.id}>
                <span>
                  <strong>{item.name}</strong>
                  <small>
                    {amount(item.quantity)} {item.unit === 'unit' ? 'un.' : item.unit} · {item.meals.join(', ')}
                    {item.notes ? ` · ${item.notes}` : ''}
                  </small>
                </span>
                <label className="pantry">
                  <input
                    type="checkbox"
                    checked={pantry.includes(item.id)}
                    disabled={!!busy}
                    onChange={() => onPantry(item.id)}
                  />
                  Já tenho
                </label>
              </li>
            ))}
          </ul>
          <button
            className="button primary full"
            disabled={!!busy || !ingredients.length || pantry.length === ingredients.length}
            onClick={onBuild}
          >
            <Icon name="bag" size={18} />
            Adicionar ao carrinho
            <Icon name="arrow" size={18} />
          </button>
          <p className="subtle small-text">
            As alternativas são opções do plano: não entram na lista como compras obrigatórias.
          </p>
        </div>
        <div>
          <h3>Refeições do plano</h3>
          <div className="meal-grid">
            {plan.meals.map((meal, index) => (
              <article className="meal-card" key={index}>
                <span className="eyebrow muted">{meal.day}</span>
                <h3>{meal.name}</h3>
                <ul>
                  {meal.ingredients.map(ingredient => (
                    <li key={ingredient.id}>
                      {ingredient.name} <span>{quantity(ingredient)}</span>
                    </li>
                  ))}
                </ul>
                {meal.alternative_groups?.map((group, groupIndex) => (
                  <div className="alternatives" key={groupIndex}>
                    <strong>Escolher {group.choose} alternativa(s)</strong>
                    {group.options.map((option, optionIndex) => (
                      <p key={optionIndex}>
                        {option.name}:{' '}
                        {option.ingredients
                          .map(ingredient => `${ingredient.name} (${quantity(ingredient)})`)
                          .join(', ')}
                      </p>
                    ))}
                  </div>
                ))}
              </article>
            ))}
          </div>
        </div>
      </div>
    </>
  )
}
