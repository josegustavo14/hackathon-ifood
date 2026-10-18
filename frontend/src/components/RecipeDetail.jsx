import React from 'react'
import Icon from './Icon'
import NutritionPanel from './NutritionPanel'
import { amount } from '../utils'

export default function RecipeDetail({
  recipe,
  servings,
  pantry,
  nutrition,
  busy,
  onServings,
  onPantry,
  onBuild,
  onNutrition,
}) {
  return (
    <>
      <p className="subtle">{recipe.description}</p>
      <div className="detail-grid">
        <div>
          <div className="ingredient-heading">
            <h3>Ingredientes</h3>
            <label className="servings">
              {recipe.source === 'recipenlg_batch' ? 'Lotes' : 'Porções'}{' '}
              <input
                type="number"
                min="1"
                max="100"
                step="1"
                value={servings}
                disabled={!!busy}
                onChange={event => onServings(event.target.value === '' ? '' : Number(event.target.value))}
              />
            </label>
          </div>
          <p className="subtle small-text">Marque “já tenho” para retirar um ingrediente da compra.</p>
          <ul className="ingredient-list">
            {recipe.ingredients.map(item => (
              <li key={item.id}>
                <span>
                  <strong>{item.name}</strong>
                  <small>
                    {amount((Number(item.quantity) * Number(servings || 0)) / recipe.servings)}{' '}
                    {item.unit === 'unit' ? 'un.' : item.unit}
                    {item.optional ? ' · opcional' : ''}
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
            disabled={
              !!busy ||
              !Number.isInteger(servings) ||
              servings < 1 ||
              servings > 100 ||
              pantry.length === recipe.ingredients.length
            }
            onClick={onBuild}
          >
            <Icon name="bag" size={18} />
            Montar minha lista de compras
            <Icon name="arrow" size={18} />
          </button>
        </div>
        <div>
          <h3>Modo de preparo</h3>
          <ol className="instructions">
            {recipe.instructions.map((step, index) => (
              <li key={index}>
                <span>{index + 1}</span>
                <p>{step}</p>
              </li>
            ))}
          </ol>
          <button
            className="button secondary"
            disabled={!!busy || !Number.isInteger(servings) || servings < 1 || servings > 100}
            onClick={onNutrition}
          >
            Ver nutrição
          </button>
          {nutrition && <NutritionPanel calculation={nutrition} />}
        </div>
      </div>
    </>
  )
}
