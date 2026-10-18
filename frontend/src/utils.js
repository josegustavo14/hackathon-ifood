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
