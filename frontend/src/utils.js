export const money = value => new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(value)
export const amount = value => new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 2 }).format(value)
export const quantity = ingredient =>
  `${amount(ingredient.quantity)} ${ingredient.unit === 'unit' ? 'un.' : ingredient.unit}`

// Keep decimal strings from the API intact. Subtotals are always recalculated by the backend.
export function excludePantry(shoppingList, pantry) {
  const items = shoppingList.items.filter(item => !pantry.includes(item.ingredient.id))
  return {
    ...shoppingList,
    items,
    unresolved_ingredients: items.map(item => item.ingredient),
    estimated_subtotal: '0.00',
    status: 'pending',
  }
}

export function validatePdf(file) {
  if (!file || !/\.pdf$/i.test(file.name) || (file.type && file.type !== 'application/pdf'))
    return 'Selecione um arquivo PDF.'
  if (file.size > 10 * 1024 * 1024) return 'O PDF deve ter no máximo 10 MiB.'
  return null
}

const round = value => Math.round(value * 1000) / 1000

const plain = value => value.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim()

// A meal repeats during the week, so a purchase covers quantity × frequency_per_week.
// Alternatives stay out of the list: they are options, not obligatory purchases.
export function planIngredients(plan) {
  const groups = new Map()
  for (const meal of plan.meals ?? []) {
    const times = meal.frequency_per_week ?? 1
    for (const ingredient of meal.ingredients) {
      const key = `${plain(ingredient.name)}|${ingredient.unit}`
      const group = groups.get(key)
      if (group) {
        group.quantity += Number(ingredient.quantity) * times
        if (!group.meals.includes(meal.name)) group.meals.push(meal.name)
        continue
      }
      groups.set(key, {
        id: ingredient.id,
        name: ingredient.name,
        quantity: Number(ingredient.quantity) * times,
        unit: ingredient.unit,
        optional: false,
        notes: ingredient.notes ?? null,
        meals: [meal.name],
      })
    }
  }
  const used = new Set()
  return [...groups.values()].map(group => {
    let id = group.id
    for (let suffix = 2; used.has(id); suffix += 1) id = `${group.id}-${suffix}`
    used.add(id)
    return { ...group, id, quantity: round(group.quantity) }
  })
}

// Build the contract the matching endpoint expects. A plan has no recipe to calculate from,
// and a recipe the Chef found on the web is not in the catalog that /shopping/calculate reads.
function shoppingList(id, recipeId, ingredients) {
  const contract = ingredients.map(({ id, name, quantity, unit, optional, notes }) => ({
    id,
    name,
    quantity: String(quantity),
    unit,
    optional: optional ?? false,
    notes: notes ?? null,
  }))
  return {
    id,
    recipe_id: recipeId,
    items: contract.map(ingredient => ({
      ingredient,
      selected_product: null,
      purchase_quantity: 0,
      total_price: '0.00',
      status: 'pending',
    })),
    estimated_subtotal: '0.00',
    currency: 'BRL',
    unresolved_ingredients: contract,
    status: 'pending',
  }
}

export function planShoppingList(plan, pantry) {
  return shoppingList(
    `shopping-${plan.id}`,
    null,
    planIngredients(plan).filter(item => !pantry.includes(item.id)),
  )
}

export function recipeShoppingList(recipe, servings, pantry) {
  const scaled = recipe.ingredients
    .filter(ingredient => !pantry.includes(ingredient.id))
    .map(ingredient => ({
      ...ingredient,
      quantity: round((Number(ingredient.quantity) * servings) / recipe.servings),
    }))
  return shoppingList(`shopping-${recipe.id}-${servings}`, null, scaled)
}
