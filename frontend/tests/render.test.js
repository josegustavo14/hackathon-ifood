import test from 'node:test'
import assert from 'node:assert/strict'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

test('the homepage and its JSX components render with the actual Vite configuration', async () => {
  const server = await createServer({
    server: { middlewareMode: true, hmr: false, watch: null },
    appType: 'custom',
    optimizeDeps: { noDiscovery: true },
  })
  try {
    const { default: App } = await server.ssrLoadModule('/src/App.jsx')
    const { default: NutritionPanel } = await server.ssrLoadModule('/src/components/NutritionPanel.jsx')
    const { default: ShoppingCartItem } = await server.ssrLoadModule('/src/components/ShoppingCartItem.jsx')
    const html = renderToStaticMarkup(React.createElement(App))
    assert.match(html, /O que vamos/)
    assert.match(html, /Comece por uma receita/)
    assert.match(html, /Navegação principal/)

    const complete = renderToStaticMarkup(
      React.createElement(NutritionPanel, {
        calculation: {
          status: 'complete',
          per_serving: {
            calories_kcal: '500',
            protein_g: '25',
            carbohydrates_g: '60',
            fat_g: '15',
            reference_quantity: '1',
            reference_unit: 'serving',
            source: 'mock_ep00',
            estimated: true,
          },
          warnings: [],
        },
      }),
    )
    assert.match(complete, /500/)
    assert.match(complete, /por porção/)
    assert.doesNotMatch(complete, /NaN/)

    const incomplete = renderToStaticMarkup(
      React.createElement(NutritionPanel, {
        calculation: {
          status: 'incomplete',
          per_serving: null,
          unresolved_ingredients: [{ name: 'muçarela' }],
          warnings: ['Faltam dados nutricionais.'],
        },
      }),
    )
    assert.match(incomplete, /muçarela/)
    assert.match(incomplete, /Faltam dados nutricionais/)
    assert.doesNotMatch(incomplete, /kcal|NaN/)

    const { default: MealPlanDetail } = await server.ssrLoadModule('/src/components/MealPlanDetail.jsx')
    const { default: Modal } = await server.ssrLoadModule('/src/components/Modal.jsx')
    const plan = {
      id: 'meal-plan-exemplo',
      source_filename: 'plano.pdf',
      extraction_warnings: [],
      meals: [
        {
          day: 'Segunda',
          name: 'Almoço',
          frequency_per_week: 2,
          ingredients: [{ id: 'rice', name: 'Arroz', quantity: '100', unit: 'g' }],
          alternative_groups: [],
        },
      ],
    }
    const planMarkup = renderToStaticMarkup(
      React.createElement(
        Modal,
        { title: 'Seu plano alimentar', onClose: () => {} },
        React.createElement(MealPlanDetail, { plan, pantry: [], busy: '', onPantry: () => {}, onBuild: () => {} }),
      ),
    )
    assert.match(planMarkup, /Seu plano alimentar/)
    assert.match(planMarkup, /Lista de compras/)
    // The weekly total, not the per-meal quantity, is what the shopper buys.
    assert.match(planMarkup, /200 g/)
    assert.match(planMarkup, /Adicionar ao carrinho/)
    assert.match(planMarkup, /Já tenho/)
    assert.doesNotMatch(planMarkup, /NaN/)
    const choice = renderToStaticMarkup(
      React.createElement(ShoppingCartItem, {
        item: {
          ingredient: { id: 'tomato', name: 'Tomate picado', quantity: '2', unit: 'unit' },
          selected_product: null,
          suggested_products: [
            {
              id: 'catalog-tomato',
              merchant_id: 'market-a',
              merchant_name: 'Mercado A',
              name: 'Tomate',
              price: '8.50',
              package_quantity: null,
              package_unit: null,
            },
          ],
          total_price: '0.00',
          reason: 'package_quantity_unknown',
        },
        merchantId: null,
        busy: '',
        onSelect: () => {},
        onSwitchMerchant: () => {},
      }),
    )
    assert.match(choice, /Tomate picado/)
    assert.match(choice, /Mercado A/)
    assert.match(choice, /Adicionar à proposta/)
  } finally {
    await server.close()
  }
})
