import React, { useEffect, useRef, useState } from 'react'
import { api } from './services/api'
import Icon from './components/Icon'
import MealPlanDetail from './components/MealPlanDetail'
import Modal from './components/Modal'
import RecipeArt from './components/RecipeArt'
import RecipeDetail from './components/RecipeDetail'
import { excludePantry, money, planShoppingList, quantity, recipeShoppingList, validatePdf } from './utils'
import ShoppingCartItem from './components/ShoppingCartItem'
import './styles.css'

const tabs = [
  { id: 'recipes', label: 'Receitas', icon: 'book' },
  { id: 'chat', label: 'Chef assistente', icon: 'chat' },
  { id: 'cart', label: 'Minha lista', icon: 'bag' },
]

const CHEF_BUSY = 'O Chef está respondendo'
const PLAN_BUSY = 'O Chef está lendo seu plano alimentar'

export default function App() {
  const [tab, setTab] = useState('recipes')
  const [query, setQuery] = useState('lasanha')
  const [recipes, setRecipes] = useState([])
  const [searched, setSearched] = useState(false)
  const [recipe, setRecipe] = useState(null)
  const [recipeModal, setRecipeModal] = useState(false)
  const [servings, setServings] = useState(4)
  const [pantry, setPantry] = useState([])
  const [plan, setPlan] = useState(null)
  const [planPantry, setPlanPantry] = useState([])
  const [origin, setOrigin] = useState(null)
  const [nutrition, setNutrition] = useState(null)
  const [shopping, setShopping] = useState(null)
  const [pendingShopping, setPendingShopping] = useState(null)
  const [addresses, setAddresses] = useState([])
  const [selectedAddress, setSelectedAddress] = useState('')
  const [mockMode, setMockMode] = useState(true)
  const [proposal, setProposal] = useState(null)
  const [confirmed, setConfirmed] = useState(false)
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      text: 'Olá! Sou seu Chef assistente. O que você quer preparar hoje? Você também pode explorar receitas e montar sua lista de compras.',
    },
  ])
  const [message, setMessage] = useState('')
  const [session, setSession] = useState(null)
  const [pdf, setPdf] = useState(null)
  const fileInput = useRef(null)
  const chatEnd = useRef(null)
  const recipeDetail = useRef(null)
  const openedPlan = useRef(null)
  const lock = useRef(false)

  useEffect(() => {
    const controller = new AbortController()
    lock.current = true
    setBusy('Buscando receitas')
    api
      .searchRecipes('lasanha', controller.signal)
      .then(data => {
        setRecipes(data)
        setSearched(true)
      })
      .catch(err => {
        if (err.name !== 'AbortError') setError(err.message)
      })
      .finally(() => {
        lock.current = false
        setBusy('')
      })
    return () => controller.abort()
  }, [])

  useEffect(() => {
    api
      .health()
      .then(data => setMockMode(data.mock_mode))
      .catch(() => {})
  }, [])

  const chefThinking = busy === CHEF_BUSY || busy === PLAN_BUSY

  useEffect(() => {
    if (tab === 'chat') chatEnd.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [messages, tab, chefThinking])

  useEffect(() => {
    if (recipe && !recipeModal && tab === 'recipes')
      recipeDetail.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [recipe, recipeModal, tab])

  async function run(label, action) {
    if (lock.current) return
    lock.current = true
    setBusy(label)
    setError('')
    try {
      await action()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy('')
      lock.current = false
    }
  }

  function invalidateCart() {
    setShopping(null)
    setPendingShopping(null)
    setAddresses([])
    setSelectedAddress('')
    setProposal(null)
    setConfirmed(false)
    setResult(null)
  }

  /** The chat opens a recipe in a modal; the catalog keeps it inline below the grid. */
  async function openRecipe(value, asModal = false) {
    await run('Carregando receita', async () => {
      const data = typeof value === 'object' ? value : await api.getRecipe(value)
      setRecipe(data)
      setServings(data.servings)
      setPantry([])
      setNutrition(null)
      invalidateCart()
      setRecipeModal(asModal)
      if (!asModal) setTab('recipes')
    })
  }

  function openPlan(value) {
    if (openedPlan.current !== value) {
      openedPlan.current = value
      setPlanPantry([])
    }
    setPlan(value)
  }

  function togglePantry(setter) {
    return id => {
      setter(prev => (prev.includes(id) ? prev.filter(item => item !== id) : [...prev, id]))
      invalidateCart()
    }
  }

  async function startShopping(list, origin) {
    if (!list.items.length)
      throw new Error('Você já tem todos os ingredientes! Desmarque algum item para gerar uma lista de compras.')
    const mode = await api.health()
    setMockMode(mode.mock_mode)
    if (mode.mock_mode) {
      setShopping(await api.match(list))
    } else {
      const saved = (await api.addresses()).addresses
      if (!saved.length) throw new Error('Cadastre um endereço de entrega no iFood para buscar produtos próximos.')
      if (saved.length === 1) {
        setSelectedAddress(saved[0].address_id)
        setShopping(await api.match(list, saved[0].address_id))
      } else {
        setAddresses(saved)
        setPendingShopping(list)
      }
    }
    setProposal(null)
    setResult(null)
    setConfirmed(false)
    setRecipeModal(false)
    setPlan(null)
    setOrigin(origin)
    setTab('cart')
  }

  async function buildShopping() {
    const origin = recipeModal ? 'recipe-modal' : 'recipe'
    await run('Calculando ingredientes e produtos', async () => {
      // A recipe the Chef found on the web is not in the catalog that /shopping/calculate reads.
      await startShopping(
        recipe.source === 'llm_web'
          ? recipeShoppingList(recipe, servings, pantry)
          : excludePantry(await api.calculate(recipe.id, servings), pantry),
        origin,
      )
    })
  }

  async function buildPlanShopping() {
    await run('Calculando ingredientes e produtos', async () => {
      await startShopping(planShoppingList(plan, planPantry), 'plan')
    })
  }

  /** Editing the ingredients means going back to whatever produced the list. */
  function editIngredients() {
    if (origin === 'plan') openPlan(openedPlan.current)
    else if (origin === 'recipe-modal') setRecipeModal(true)
    else setTab('recipes')
  }

  async function matchAtSelectedAddress() {
    await run('Buscando produtos para o endereço', async () => {
      if (!selectedAddress) throw new Error('Escolha o endereço de entrega antes de buscar produtos.')
      setShopping(await api.match(pendingShopping, selectedAddress))
      setPendingShopping(null)
    })
  }

  async function sendChat(event) {
    event.preventDefault()
    if (pdf) {
      await sendPlan(pdf)
      return
    }
    const text = message.trim()
    if (!text) return
    await run(CHEF_BUSY, async () => {
      setMessages(prev => [...prev, { role: 'user', text }])
      setMessage('')
      try {
        const response = await api.chat(text, session, {
          recipe_id: recipe?.id ?? null,
          servings,
          pantry_ingredient_ids: pantry,
        })
        setSession(response.session_id)
        setMessages(prev => [
          ...prev,
          {
            role: 'assistant',
            text: response.message,
            recipe: response.recipe,
            nutrition: response.nutrition,
            status: response.status,
          },
        ])
      } catch (err) {
        setMessage(text)
        setMessages(prev => [
          ...prev,
          {
            role: 'assistant',
            text: 'Não consegui enviar sua mensagem. O texto foi preservado para você tentar novamente.',
          },
        ])
        throw err
      }
    })
  }

  function selectPdf(file) {
    const validation = validatePdf(file)
    if (validation) {
      setError(validation)
      return
    }
    setError('')
    setPdf(file)
    setTab('chat')
  }

  async function sendPlan(file) {
    await run(PLAN_BUSY, async () => {
      setMessages(prev => [...prev, { role: 'user', text: 'Enviei meu plano alimentar em PDF.', file }])
      setPdf(null)
      try {
        const parsed = await api.parsePlan(file)
        const days = parsed.days?.length ?? 0
        setMessages(prev => [
          ...prev,
          {
            role: 'assistant',
            text: `Li seu plano alimentar: ${parsed.meals.length} refeição(ões) em ${days} dia(s). Abra o plano para revisar a lista de compras.`,
            plan: parsed,
          },
        ])
      } catch (err) {
        setPdf(file)
        setMessages(prev => [
          ...prev,
          {
            role: 'assistant',
            text: 'Não consegui ler esse PDF. O arquivo continua anexado para você tentar novamente.',
          },
        ])
        throw err
      }
    })
  }

  async function chooseSuggestedProduct(item, productId, packages) {
    await run('Atualizando proposta de compras', async () => {
      const updated = await api.selectProduct(shopping, item.ingredient.id, productId, packages, selectedAddress)
      setShopping(updated)
      setProposal(null)
      setConfirmed(false)
      setResult(null)
    })
  }

  async function switchMerchant(merchantId) {
    await run('Buscando produtos no mercado escolhido', async () => {
      const updated = await api.match(shopping, selectedAddress, merchantId)
      setShopping(updated)
      setProposal(null)
      setConfirmed(false)
      setResult(null)
    })
  }

  const count = shopping?.items.length ?? 0
  const sources = { mock_ep00: 'Receita demonstrativa', llm_web: 'Receita da web' }
  const recipeSource = recipe && (sources[recipe.source] ?? recipe.source)
  const recipeProps = {
    recipe,
    servings,
    pantry,
    nutrition,
    busy,
    onServings: value => {
      setServings(value)
      invalidateCart()
    },
    onPantry: togglePantry(setPantry),
    onBuild: buildShopping,
  }
  const merchantId = shopping?.items.find(item => item.selected_product)?.selected_product?.merchant_id || null
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a
          className="brand"
          href="#"
          onClick={e => {
            e.preventDefault()
            setTab('recipes')
          }}
          aria-label="iFood Chef AI, início"
        >
          <span className="brand-icon">
            <Icon name="chef" size={27} />
          </span>
          <span>
            <b>
              iFood <em>Chef</em>
            </b>
            <small>SEU ASSISTENTE NA COZINHA</small>
          </span>
        </a>
        <div className="nav-caption">VAMOS COZINHAR?</div>
        <nav aria-label="Navegação principal">
          {tabs.map(item => (
            <button
              key={item.id}
              className={`nav-item ${tab === item.id ? 'active' : ''}`}
              onClick={() => setTab(item.id)}
              aria-current={tab === item.id ? 'page' : undefined}
            >
              <Icon name={item.icon} />
              <span>{item.label}</span>
              {item.id === 'cart' && count > 0 && <span className="count">{count}</span>}
            </button>
          ))}
        </nav>
        <div className="sidebar-tip">
          <span className="tip-icon">
            <Icon name="leaf" />
          </span>
          <strong>
            Menos desperdício.
            <br />
            Mais sabor.
          </strong>
          <p>Use o que você já tem em casa. A gente cuida do resto da lista.</p>
        </div>
        <div className="sidebar-footer">
          <span className="status-dot" /> Hackathon SEMCOMP × iFood<small>Feito para simplificar sua rotina.</small>
        </div>
      </aside>

      <div className="main-shell">
        <header className="topbar">
          <span>
            Da ideia ao prato<span className="topbar-divider">/</span>
            <strong>{tabs.find(item => item.id === tab)?.label}</strong>
          </span>
          <span className="demo-badge">
            <span className="status-dot" /> {mockMode ? 'Modo demonstrativo' : 'iFood conectado'}
          </span>
        </header>
        <main id="main-content">
          {error && (
            <div className="alert error" role="alert">
              <span>{error}</span>
              <button className="icon-button" onClick={() => setError('')} aria-label="Fechar aviso">
                <Icon name="close" />
              </button>
            </div>
          )}
          {busy && !chefThinking && (
            <div className="busy" role="status">
              <span className="spinner" />
              {busy}…
            </div>
          )}

          {tab === 'recipes' && (
            <>
              <section className="hero">
                <div className="hero-copy">
                  <span className="eyebrow">
                    <Icon name="spark" size={16} /> UMA PITADA DE INTELIGÊNCIA
                  </span>
                  <h1>
                    O que vamos
                    <br />
                    preparar <em>hoje?</em>
                  </h1>
                  <p>Encontre sua receita, ajuste as porções e transforme os ingredientes em uma lista de compras.</p>
                  <button className="button dark" onClick={() => setTab('chat')}>
                    Pedir uma ideia ao Chef <Icon name="arrow" size={18} />
                  </button>
                </div>
                <RecipeArt />
              </section>
              <section className="recipe-section">
                <div className="section-heading">
                  <div>
                    <span className="eyebrow muted">INSPIRAÇÃO PARA A SUA MESA</span>
                    <h2>Comece por uma receita</h2>
                  </div>
                  <span className="section-note">Seu próximo prato favorito está aqui.</span>
                </div>
                <form
                  className="search-form"
                  onSubmit={event => {
                    event.preventDefault()
                    run('Buscando receitas', async () => {
                      setRecipes(await api.searchRecipes(query.trim()))
                      setSearched(true)
                    })
                  }}
                >
                  <Icon name="search" />
                  <input
                    aria-label="Buscar receitas"
                    placeholder="O que você está com vontade de comer?"
                    value={query}
                    onChange={event => setQuery(event.target.value)}
                    required
                    maxLength={200}
                  />
                  <button className="button primary" disabled={!!busy || !query.trim()}>
                    Buscar receita <Icon name="arrow" size={17} />
                  </button>
                </form>
                <div className="discovery-grid">
                  {recipes.map(item => (
                    <article className="recipe-card" key={item.id}>
                      <div className="recipe-card-art">
                        <RecipeArt small />
                        <span className="recipe-tag">CLÁSSICO DA CASA</span>
                      </div>
                      <div className="recipe-card-body">
                        <div className="recipe-meta">
                          <span>
                            <Icon name="clock" size={15} />
                            {item.preparation_time_minutes
                              ? `${item.preparation_time_minutes} min`
                              : 'Tempo não informado'}
                          </span>
                          <span>{item.servings} porções</span>
                        </div>
                        <h3>{item.name}</h3>
                        <p>{item.description || 'Uma receita para compartilhar bons momentos.'}</p>
                        <button className="text-button" disabled={!!busy} onClick={() => openRecipe(item.id)}>
                          Ver receita e ingredientes <Icon name="arrow" size={18} />
                        </button>
                      </div>
                    </article>
                  ))}
                  {searched && !recipes.length && (
                    <div className="empty-state">
                      <Icon name="search" size={32} />
                      <h3>Nenhuma receita encontrada</h3>
                      <p>Na demonstração, experimente buscar por “lasanha”.</p>
                    </div>
                  )}
                  <aside className="how-card">
                    <span className="eyebrow muted">DO SEU JEITO</span>
                    <h3>
                      Uma boa receita.
                      <br />
                      Uma lista resolvida.
                    </h3>
                    {[
                      ['01', 'Escolha e ajuste', 'Defina as porções para quem vai sentar à mesa.'],
                      ['02', 'Aproveite sua despensa', 'Marque os ingredientes que você já tem.'],
                      ['03', 'Revise sua lista', 'Confira produtos e preços antes de confirmar.'],
                    ].map(([n, title, description]) => (
                      <div className="how-step" key={n}>
                        <span>{n}</span>
                        <div>
                          <strong>{title}</strong>
                          <p>{description}</p>
                        </div>
                      </div>
                    ))}
                    <div className="how-bottom">
                      <Icon name="leaf" size={17} /> Planejar também é cuidar.
                    </div>
                  </aside>
                </div>
              </section>

              {recipe && !recipeModal && (
                <section ref={recipeDetail} className="panel recipe-detail">
                  <div className="section-heading">
                    <div>
                      <span className="eyebrow muted">MÃO NA MASSA</span>
                      <h2>{recipe.name}</h2>
                    </div>
                    <span className="pill">{recipeSource}</span>
                  </div>
                  <RecipeDetail {...recipeProps} />
                </section>
              )}
            </>
          )}

          {tab === 'chat' && (
            <section className="workspace">
              <PageHeading
                eyebrow="UMA AJUDA NA COZINHA"
                title="Converse com o Chef"
                description="Conte o que você quer preparar ou anexe o PDF do seu plano alimentar."
              />
              <div
                className="chat-panel panel"
                onDragOver={event => event.preventDefault()}
                onDrop={event => {
                  event.preventDefault()
                  if (!busy) selectPdf(event.dataTransfer.files[0])
                }}
              >
                <div className="chat-title">
                  <span className="brand-icon">
                    <Icon name="chef" />
                  </span>
                  <div>
                    <strong>Chef assistente</strong>
                    <small>Converse ou envie seu plano alimentar em PDF</small>
                  </div>
                  <span className="pill">AI</span>
                </div>
                <div className="messages" aria-live="polite" aria-label="Conversa com o Chef">
                  {messages.map((item, index) => (
                    <div key={index} className={`message ${item.role}`}>
                      <span className="message-author">{item.role === 'user' ? 'Você' : 'Chef'}</span>
                      <p>{item.text}</p>
                      {item.file && (
                        <button
                          className="text-button"
                          onClick={() => window.open(URL.createObjectURL(item.file), '_blank', 'noopener')}
                        >
                          <Icon name="clip" size={15} />
                          {item.file.name}
                        </button>
                      )}
                      {item.plan && (
                        <button className="text-button" disabled={!!busy} onClick={() => openPlan(item.plan)}>
                          Abrir plano alimentar
                          <Icon name="arrow" size={16} />
                        </button>
                      )}
                      {item.status === 'needs_input' && (
                        <small>O agente precisa de mais informações ou de uma próxima etapa.</small>
                      )}
                      {item.status === 'error' && (
                        <small role="alert">O agente não conseguiu concluir a solicitação.</small>
                      )}
                      {item.nutrition && (
                        <small>
                          Nutrição estimada: {item.nutrition.calories_kcal} kcal · {item.nutrition.protein_g} g de
                          proteína · {item.nutrition.carbohydrates_g} g de carboidratos · {item.nutrition.fat_g} g de
                          gorduras ({item.nutrition.basis === 'per_serving' ? 'por porção' : 'receita total'}).
                        </small>
                      )}
                      {item.recipe && (
                        <button className="text-button" disabled={!!busy} onClick={() => openRecipe(item.recipe, true)}>
                          Abrir {item.recipe.name}
                          <Icon name="arrow" size={16} />
                        </button>
                      )}
                    </div>
                  ))}
                  {chefThinking && (
                    <div className="message assistant thinking" role="status">
                      <span className="message-author">Chef</span>
                      <span className="thinking-dots" aria-hidden="true">
                        <i />
                        <i />
                        <i />
                      </span>
                      <span className="sr-only">O Chef está pensando na resposta…</span>
                    </div>
                  )}
                  <div ref={chatEnd} />
                </div>
                <form className="chat-form" onSubmit={sendChat}>
                  {pdf && (
                    <div className="chat-attachment">
                      <Icon name="clip" size={15} />
                      <span>{pdf.name}</span>
                      <button
                        type="button"
                        className="icon-button"
                        disabled={!!busy}
                        onClick={() => setPdf(null)}
                        aria-label={`Remover ${pdf.name}`}
                      >
                        <Icon name="close" size={15} />
                      </button>
                    </div>
                  )}
                  <label className="sr-only" htmlFor="chat-message">
                    Mensagem para o Chef
                  </label>
                  <input
                    className="sr-only"
                    id="pdf-file"
                    ref={fileInput}
                    type="file"
                    accept="application/pdf,.pdf"
                    disabled={!!busy}
                    onChange={event => {
                      if (event.target.files[0]) selectPdf(event.target.files[0])
                      event.target.value = ''
                    }}
                  />
                  <button
                    type="button"
                    className="icon-button attach"
                    disabled={!!busy}
                    onClick={() => fileInput.current.click()}
                    aria-label="Anexar plano alimentar em PDF"
                    title="Anexar plano alimentar em PDF (até 10 MiB)"
                  >
                    <Icon name="clip" size={19} />
                  </button>
                  <textarea
                    id="chat-message"
                    placeholder="Ex.: Quero fazer lasanha para quatro pessoas…"
                    aria-describedby="chat-hint"
                    rows="2"
                    maxLength={4000}
                    value={message}
                    readOnly={!!busy}
                    aria-busy={chefThinking}
                    onChange={event => setMessage(event.target.value)}
                    onKeyDown={event => {
                      if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
                        event.preventDefault()
                        if (!busy && (message.trim() || pdf)) event.currentTarget.form.requestSubmit()
                      }
                    }}
                  />
                  <button className="button primary" disabled={!!busy || (!message.trim() && !pdf)}>
                    {chefThinking ? 'Enviando…' : pdf ? 'Enviar PDF' : 'Enviar'}
                    <Icon name="arrow" size={18} />
                  </button>
                </form>
              </div>
              <p className="footnote" id="chat-hint">
                Anexe o PDF do seu plano alimentar (até 10 MiB) para o Chef extrair as refeições e os ingredientes, ou
                arraste o arquivo para a conversa.
              </p>
            </section>
          )}

          {tab === 'cart' && (
            <section className="workspace">
              <PageHeading
                eyebrow="DA RECEITA PARA O MERCADO"
                title="Sua lista, bem pensada"
                description="Confira as quantidades, os produtos e o subtotal antes de confirmar."
              />
              {pendingShopping ? (
                <div className="panel">
                  <h2>Escolha o endereço de entrega</h2>
                  <p>Selecione um endereço salvo no iFood para buscar produtos disponíveis na sua região.</p>
                  <select
                    aria-label="Endereço de entrega"
                    value={selectedAddress}
                    onChange={event => setSelectedAddress(event.target.value)}
                  >
                    <option value="">Selecione um endereço</option>
                    {addresses.map(address => (
                      <option key={address.address_id} value={address.address_id}>
                        {address.alias || address.formatted_address}
                      </option>
                    ))}
                  </select>
                  <button
                    className="button primary"
                    disabled={!!busy || !selectedAddress}
                    onClick={matchAtSelectedAddress}
                  >
                    Buscar produtos
                  </button>
                </div>
              ) : !shopping ? (
                <div className="empty-state panel">
                  <span className="empty-icon">
                    <Icon name="bag" size={38} />
                  </span>
                  <h2>Falta só escolher o que cozinhar.</h2>
                  <p>Sua lista aparece aqui depois que você escolhe uma receita e ajusta os ingredientes.</p>
                  <button className="button primary" onClick={() => setTab('recipes')}>
                    Explorar receitas
                    <Icon name="arrow" size={18} />
                  </button>
                </div>
              ) : (
                <div className="cart-layout">
                  <div className="panel cart-items">
                    <div className="section-heading">
                      <h2>Ingredientes da compra</h2>
                      <span className="pill">{count} itens</span>
                    </div>
                    {shopping.items.map(item => (
                      <ShoppingCartItem
                        key={item.ingredient.id}
                        item={item}
                        merchantId={merchantId}
                        busy={busy}
                        onSelect={(productId, packages) => chooseSuggestedProduct(item, productId, packages)}
                        onSwitchMerchant={switchMerchant}
                      />
                    ))}
                    {shopping.unresolved_ingredients.length > 0 && (
                      <div className="alert info">
                        Há ingredientes que precisam de revisão:{' '}
                        {shopping.unresolved_ingredients.map(item => item.name).join(', ')}. Escolha um produto e a
                        quantidade para cada item acima antes de gerar a proposta.
                      </div>
                    )}
                    <button className="text-button" disabled={!!busy} onClick={editIngredients}>
                      Voltar e editar ingredientes
                      <Icon name="arrow" size={17} />
                    </button>
                  </div>
                  <aside className="panel cart-summary">
                    <span className="eyebrow muted">TUDO NO SEU CONTROLE</span>
                    <h2>Resumo da lista</h2>
                    <div className="summary-line">
                      <span>Produtos selecionados</span>
                      <strong>{count}</strong>
                    </div>
                    <div className="summary-line total">
                      <span>Subtotal estimado</span>
                      <strong>{money(shopping.estimated_subtotal)}</strong>
                    </div>
                    <p className="subtle small-text">
                      {mockMode ? 'Preços demonstrativos em BRL.' : 'Preços retornados pelo iFood em BRL.'} Frete e
                      outras taxas não estão incluídos.
                    </p>
                    {!proposal && (
                      <button
                        className="button primary full"
                        disabled={
                          !!busy ||
                          shopping.status !== 'ready_for_review' ||
                          !!shopping.unresolved_ingredients.length ||
                          !count
                        }
                        onClick={() =>
                          run('Preparando proposta', async () => {
                            setProposal(await api.preview(shopping, selectedAddress))
                            setConfirmed(false)
                            setResult(null)
                          })
                        }
                      >
                        Revisar proposta
                        <Icon name="arrow" size={18} />
                      </button>
                    )}
                    {proposal && !result && (
                      <div className="confirmation">
                        <h3>Revise e autorize</h3>
                        <p>
                          Proposta com {proposal.items.length} itens e subtotal de{' '}
                          <strong>{money(proposal.estimated_subtotal)}</strong>.
                        </p>
                        <label>
                          <input
                            type="checkbox"
                            checked={confirmed}
                            disabled={!!busy}
                            onChange={event => setConfirmed(event.target.checked)}
                          />
                          <span>Revisei os itens e autorizo a aplicação desta proposta.</span>
                        </label>
                        <button
                          className="button primary full"
                          disabled={!!busy || !confirmed || proposal.status !== 'ready_for_review'}
                          onClick={() =>
                            run('Aplicando proposta', async () => {
                              if (!confirmed) return
                              const response = await api.apply(proposal)
                              setResult(response)
                              setProposal(response.proposal)
                              setConfirmed(false)
                            })
                          }
                        >
                          Confirmar proposta
                          <Icon name="check" size={18} />
                        </button>
                        <small>
                          {mockMode
                            ? 'A aplicação nesta etapa é apenas simulada.'
                            : 'Após confirmar, os itens serão adicionados ao carrinho do iFood. Nenhum pedido será enviado.'}
                        </small>
                      </div>
                    )}
                    {result && (
                      <div className="success" role="status">
                        <Icon name="check" size={26} />
                        <h3>{result.mock_only ? 'Simulação concluída!' : 'Proposta processada'}</h3>
                        <p>{result.message}</p>
                        {result.mock_only ? (
                          <small>Nenhum carrinho real foi alterado.</small>
                        ) : (
                          <small>ID do carrinho: {result.cart_id}</small>
                        )}
                      </div>
                    )}
                    <div className="summary-note">
                      <Icon name="leaf" size={18} />
                      <p>Os ingredientes que você já tem ficam fora da compra.</p>
                    </div>
                  </aside>
                </div>
              )}
            </section>
          )}
          {recipe && recipeModal && (
            <Modal
              title={recipe.name}
              eyebrow="MÃO NA MASSA"
              badge={recipeSource}
              onClose={() => setRecipeModal(false)}
            >
              <RecipeDetail {...recipeProps} />
            </Modal>
          )}
          {plan && (
            <Modal
              title="Seu plano alimentar"
              eyebrow="DO PLANO PARA O MERCADO"
              badge={`${plan.meals.length} refeições`}
              onClose={() => setPlan(null)}
            >
              <MealPlanDetail
                plan={plan}
                pantry={planPantry}
                busy={busy}
                onPantry={togglePantry(setPlanPantry)}
                onBuild={buildPlanShopping}
              />
            </Modal>
          )}
          <footer className="page-footer">
            <span className="footer-brand">
              iFood <em>Chef AI</em>
            </span>
            <span>
              {mockMode
                ? 'Receitas, produtos e preços demonstrativos'
                : 'Dados de receitas e ofertas conforme as fontes indicadas'}
            </span>
            <span>Da sua ideia à sua mesa.</span>
          </footer>
        </main>
      </div>
    </div>
  )
}

function PageHeading({ eyebrow, title, description }) {
  return (
    <div className="page-heading">
      <span className="eyebrow muted">{eyebrow}</span>
      <h1>{title}</h1>
      <p>{description}</p>
    </div>
  )
}
