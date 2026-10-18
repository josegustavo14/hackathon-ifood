import { afterEach, test } from 'node:test'
import assert from 'node:assert/strict'
import { api, API_BASE_URL } from '../src/services/api.js'

const originalFetch = globalThis.fetch
afterEach(() => { globalThis.fetch = originalFetch })

test('shopping flow transports server decimal strings through matching and preview', async () => {
  const calls = []
  const calculated = { id: 'list', items: [], estimated_subtotal: '0.00' }
  const matched = { ...calculated, estimated_subtotal: '70.90', status: 'ready_for_review' }
  const proposal = { id: 'proposal', estimated_subtotal: '70.90', status: 'ready_for_review', requires_confirmation: true }
  const responses = [calculated, matched, proposal]
  globalThis.fetch = async (url, options) => {
    calls.push({ url, body: JSON.parse(options.body) })
    return new Response(JSON.stringify(responses.shift()), { status: 200 })
  }
  const list = await api.calculate('mock-lasagna-bolognese', 4)
  const products = await api.match(list)
  const preview = await api.preview(products)
  assert.deepEqual(calls.map(call => call.url), ['/shopping/calculate', '/shopping/match', '/cart/preview'].map(path => API_BASE_URL + path))
  assert.deepEqual(calls[0].body, { recipe_id: 'mock-lasagna-bolognese', servings: 4 })
  assert.deepEqual(calls[1].body, { shopping_list: calculated, merchant_id: null })
  assert.equal(calls[2].body.shopping_list.estimated_subtotal, '70.90')
  assert.equal(preview.requires_confirmation, true)
  // Generating a proposal never invokes /cart/apply.
  assert.equal(calls.length, 3)
})

test('apply sends explicit confirmation and preserves the server mock_only response', async () => {
  const proposal = { id: 'proposal', status: 'ready_for_review', estimated_subtotal: '70.90' }
  globalThis.fetch = async (url, options) => {
    assert.equal(url, API_BASE_URL + '/cart/apply')
    assert.deepEqual(JSON.parse(options.body), { proposal, confirmed: true })
    return new Response(JSON.stringify({ proposal: { ...proposal, status: 'applied' }, mock_only: true, message: 'Simulado' }))
  }
  assert.equal((await api.apply(proposal)).mock_only, true)
})

test('chat preserves session and structured context', async () => {
  globalThis.fetch = async (url, options) => {
    assert.equal(url, API_BASE_URL + '/agent/chat')
    assert.deepEqual(JSON.parse(options.body), { message: 'Quero lasanha', session_id: 'session-1', context: { servings: 4 } })
    return new Response(JSON.stringify({ session_id: 'session-1', message: 'Exemplo', status: 'needs_input' }))
  }
  assert.equal((await api.chat('Quero lasanha', 'session-1', { servings: 4 })).status, 'needs_input')
})

test('PDF upload uses the multipart file field and lets fetch set its boundary', async () => {
  globalThis.fetch = async (url, options) => {
    assert.equal(url, API_BASE_URL + '/meal-plans/parse')
    assert.equal(options.headers, undefined)
    assert.ok(options.body instanceof FormData)
    assert.equal(options.body.get('file').name, 'plano.pdf')
    assert.equal(options.body.get('file').type, 'application/pdf')
    return new Response(JSON.stringify({ id: 'plan', meals: [] }))
  }
  await api.parsePlan(new File(['%PDF-1.4'], 'plano.pdf'))
})

test('API envelope and connection failures provide useful errors', async () => {
  globalThis.fetch = async () => new Response(JSON.stringify({ error: { message: 'Invalid request', details: [{ msg: 'servings must be positive' }] } }), { status: 422 })
  await assert.rejects(api.calculate('recipe', 0), /servings must be positive/)
  globalThis.fetch = async () => { throw new TypeError('fetch failed') }
  await assert.rejects(api.searchRecipes('lasanha'), /Verifique se o backend está rodando/)
})

test('search encodes user input as a query parameter', async () => {
  globalThis.fetch = async url => {
    assert.equal(new URL(url).searchParams.get('q'), 'arroz & feijão')
    return new Response('[]')
  }
  assert.deepEqual(await api.searchRecipes('arroz & feijão'), [])
})
