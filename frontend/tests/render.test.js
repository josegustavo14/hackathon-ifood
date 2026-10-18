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
    const html = renderToStaticMarkup(React.createElement(App))
    assert.match(html, /O que vamos/)
    assert.match(html, /Comece por uma receita/)
    assert.match(html, /Navegação principal/)
  } finally {
    await server.close()
  }
})
