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
    const html = renderToStaticMarkup(React.createElement(App))
    assert.match(html, /O que vamos/)
    assert.match(html, /Comece por uma receita/)
    assert.match(html, /Navegação principal/)

    const complete = renderToStaticMarkup(React.createElement(NutritionPanel, { calculation: {
      status: 'complete', per_serving: {
        calories_kcal: '500', protein_g: '25', carbohydrates_g: '60', fat_g: '15',
        reference_quantity: '1', reference_unit: 'serving', source: 'mock_ep00', estimated: true,
      }, warnings: [],
    } }))
    assert.match(complete, /500/)
    assert.match(complete, /por porção/)
    assert.doesNotMatch(complete, /NaN/)

    const incomplete = renderToStaticMarkup(React.createElement(NutritionPanel, { calculation: {
      status: 'incomplete', per_serving: null,
      unresolved_ingredients: [{ name: 'muçarela' }], warnings: ['Faltam dados nutricionais.'],
    } }))
    assert.match(incomplete, /muçarela/)
    assert.match(incomplete, /Faltam dados nutricionais/)
    assert.doesNotMatch(incomplete, /kcal|NaN/)
  } finally {
    await server.close()
  }
})
