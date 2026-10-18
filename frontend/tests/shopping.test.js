import test from 'node:test'
import assert from 'node:assert/strict'
import { excludePantry, validatePdf, money } from '../src/utils.js'

test('pantry exclusions preserve decimal strings and remove unresolved items before matching', () => {
  const list = { id: 'list', estimated_subtotal: '0.00', status: 'pending', items: [
    { ingredient: { id: 'pasta', quantity: '250.00' }, total_price: '0.00' },
    { ingredient: { id: 'beef', quantity: '500.00' }, total_price: '0.00' },
  ], unresolved_ingredients: [] }
  const filtered = excludePantry(list, ['beef'])
  assert.deepEqual(filtered.items.map(item => item.ingredient.id), ['pasta'])
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
