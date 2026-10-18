import test from 'node:test'
import assert from 'node:assert/strict'
import {
  excludePantry,
  planIngredients,
  planShoppingList,
  recipeShoppingList,
  validatePdf,
  money,
  multiplyMoney,
} from '../src/utils.js'
import { defaultRecipe } from '../src/defaultRecipe.js'

test('the default pasta recipe scales into a shopping request without a catalog recipe ID', () => {
  const list = recipeShoppingList(defaultRecipe, 2, ['cream'])
  assert.equal(list.recipe_id, null)
  assert.deepEqual(
    list.items.map(item => [item.ingredient.name, item.ingredient.quantity]),
    [
      ['Macarrão', '250'],
      ['Molho de tomate', '150'],
      ['Carne moída', '250'],
    ],
  )
  assert.equal(list.estimated_subtotal, '0.00')
  assert.equal(list.unresolved_ingredients.length, 3)
  assert.ok(list.items.every(item => item.status === 'pending' && item.selected_product === null))
})

test('pantry exclusions preserve decimal strings and remove unresolved items before matching', () => {
  const list = {
    id: 'list',
    estimated_subtotal: '0.00',
    status: 'pending',
    items: [
      { ingredient: { id: 'pasta', quantity: '250.00' }, total_price: '0.00' },
      { ingredient: { id: 'beef', quantity: '500.00' }, total_price: '0.00' },
    ],
    unresolved_ingredients: [],
  }
  const filtered = excludePantry(list, ['beef'])
  assert.deepEqual(
    filtered.items.map(item => item.ingredient.id),
    ['pasta'],
  )
  assert.deepEqual(filtered.unresolved_ingredients, [list.items[0].ingredient])
  assert.equal(filtered.items[0].ingredient.quantity, '250.00')
  assert.equal(filtered.estimated_subtotal, '0.00')
  assert.equal(list.items.length, 2)
  assert.equal(excludePantry(list, ['pasta', 'beef']).items.length, 0)
})

test('PDF validation accepts the size boundary and rejects invalid type and oversized files', () => {
  assert.equal(validatePdf({ name: 'plano.PDF', type: 'application/pdf', size: 10 * 1024 * 1024 }), null)
  assert.equal(validatePdf({ name: 'plano.pdf', type: '', size: 1 }), null)
  assert.ok(validatePdf({ name: 'plano.pdf', type: 'application/pdf', size: 10 * 1024 * 1024 + 1 }))
  assert.ok(validatePdf({ name: 'plano.png', type: 'image/png', size: 1 }))
  assert.ok(validatePdf({ name: 'plano.pdf', type: 'text/html', size: 1 }))
  assert.ok(validatePdf(undefined))
})

test('formats API monetary strings in BRL without recomputing the subtotal', () => {
  assert.match(money('70.90'), /70,90/)
  assert.match(money('0.00'), /0,00/)
})

test('a meal plan becomes one weekly purchase per ingredient, without alternatives', () => {
  const plan = {
    id: 'meal-plan-exemplo',
    meals: [
      {
        day: 'Segunda',
        name: 'Café da manhã',
        frequency_per_week: 7,
        ingredients: [{ id: 'oats', name: 'Aveia', quantity: '40', unit: 'g', notes: null }],
        alternative_groups: [
          {
            choose: 1,
            options: [{ name: 'Banana', ingredients: [{ id: 'banana', name: 'Banana', quantity: '1', unit: 'unit' }] }],
          },
        ],
      },
      {
        day: 'Terça',
        name: 'Almoço',
        frequency_per_week: 2,
        ingredients: [
          { id: 'rice', name: 'Arroz', quantity: '100', unit: 'g' },
          { id: 'oats-again', name: 'aveia', quantity: '10', unit: 'g' },
        ],
      },
    ],
  }
  const ingredients = planIngredients(plan)
  assert.deepEqual(
    ingredients.map(item => [item.id, item.quantity, item.unit]),
    [
      ['oats', 300, 'g'],
      ['rice', 200, 'g'],
    ],
  )
  // Accented or differently cased names are the same purchase, and the meals that need it are kept.
  assert.deepEqual(ingredients[0].meals, ['Café da manhã', 'Almoço'])
  assert.ok(!ingredients.some(item => item.name === 'Banana'))

  const list = planShoppingList(plan, ['oats'])
  assert.equal(list.recipe_id, null)
  assert.equal(list.status, 'pending')
  assert.equal(list.estimated_subtotal, '0.00')
  assert.deepEqual(
    list.items.map(item => item.ingredient.id),
    ['rice'],
  )
  assert.deepEqual(list.unresolved_ingredients, [list.items[0].ingredient])
  // The backend contract forbids extra keys, so the UI-only metadata must not reach the request.
  assert.deepEqual(Object.keys(list.items[0].ingredient), ['id', 'name', 'quantity', 'unit', 'optional', 'notes'])
  assert.equal(planShoppingList(plan, ['oats', 'rice']).items.length, 0)
})

test('manual package prices multiply exactly before display', () => {
  assert.equal(multiplyMoney('8.35', 3), '25.05')
  assert.equal(multiplyMoney('0.99', 3), '2.97')
  assert.equal(multiplyMoney('4.00', 0), '0.00')
})
