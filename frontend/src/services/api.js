export const API_BASE_URL = (import.meta.env?.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1').replace(/\/$/, '')
const API_ROOT_URL = API_BASE_URL.replace(/\/api\/v1$/, '')

async function request(path, { body, root = false, ...options } = {}) {
  let response
  try {
    response = await fetch(`${root ? API_ROOT_URL : API_BASE_URL}${path}`, {
      ...options,
      credentials: 'include',
      ...(body instanceof FormData
        ? { body }
        : body === undefined
          ? {}
          : { body: JSON.stringify(body), headers: { 'Content-Type': 'application/json' } }),
    })
  } catch (error) {
    if (error.name === 'AbortError') throw error
    throw new Error('Não foi possível conectar à API. Verifique se o backend está rodando em ' + API_BASE_URL + '.')
  }
  const data = await response.json().catch(() => null)
  if (!response.ok) {
    const details = data?.error?.details
      ?.map(item => item.msg)
      .filter(Boolean)
      .join('; ')
    throw new Error(
      details || data?.error?.message || data?.detail || `A API retornou o erro ${response.status}. Tente novamente.`,
    )
  }
  if (data === null) throw new Error('A API retornou uma resposta inválida.')
  return data
}

/** @type {import('../types/api').ChefApi} */
export const api = {
  health: () => request('/health', { root: true }),
  addresses: () => request('/ifood/addresses'),
  searchRecipes: (query, signal) => request(`/recipes/search?q=${encodeURIComponent(query)}`, { signal }),
  getRecipe: id => request(`/recipes/${encodeURIComponent(id)}`),
  nutrition: (recipe_id, servings) =>
    request('/nutrition/calculate', { method: 'POST', body: { recipe_id, servings } }),
  calculate: (recipe_id, servings) => request('/shopping/calculate', { method: 'POST', body: { recipe_id, servings } }),
  match: (shopping_list, address_id = null) => request('/shopping/match', { method: 'POST', body: { shopping_list, merchant_id: null, ...(address_id ? { address_id } : {}) } }),
  preview: (shopping_list, address_id = null) => request('/cart/preview', { method: 'POST', body: { shopping_list, ...(address_id ? { address_id } : {}) } }),
  apply: proposal => request('/cart/apply', { method: 'POST', body: { proposal, confirmed: true } }),
  chat: (message, session_id, context) =>
    request('/agent/chat', { method: 'POST', body: { message, session_id, context } }),
  parsePlan: file => {
    const body = new FormData()
    body.append('file', file.type ? file : new File([file], file.name, { type: 'application/pdf' }))
    return request('/meal-plans/parse', { method: 'POST', body })
  },
}
