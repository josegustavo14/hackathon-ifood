import React, { useEffect, useRef, useState } from 'react'
import { api } from './services/api'
import Icon from './components/Icon'
import MealPlanDetail from './components/MealPlanDetail'
import Modal from './components/Modal'
import { defaultRecipe } from './defaultRecipe'
import RecipeDetail from './components/RecipeDetail'
import { money, planShoppingList, recipeShoppingList, validatePdf } from './utils'
import ShoppingCartItem from './components/ShoppingCartItem'
import './styles.css'

const tabs = [
  { id: 'chat', label: 'Conversa', icon: 'chat' },
  { id: 'cart', label: 'Minha lista', icon: 'bag' },
]

const CHEF_BUSY = 'O Chef está respondendo'
const PLAN_BUSY = 'O Chef está lendo seu plano alimentar'

export default function App() {
  const [tab, setTab] = useState('chat')
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
  const [result, setResult] = useState(null)
  const [checkout, setCheckout] = useState(null)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      text: 'O que você quer cozinhar? Escreva aqui ou envie seu plano alimentar em PDF.',
    },
  ])
  const [message, setMessage] = useState('')
  const [session, setSession] = useState(null)
  const [pdf, setPdf] = useState(null)
  const fileInput = useRef(null)
  const chatEnd = useRef(null)
  const openedPlan = useRef(null)
  const lock = useRef(false)

  const chefThinking = busy === CHEF_BUSY || busy === PLAN_BUSY

  useEffect(() => {
    if (tab === 'chat') chatEnd.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [messages, tab, chefThinking])

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
    setResult(null)
    setCheckout(null)
  }

  async function openRecipe(value) {
    await run('Carregando receita', async () => {
      const data = typeof value === 'object' ? value : await api.getRecipe(value)
      setRecipe(data)
      setServings(data.servings)
      setPantry([])
      setNutrition(null)
      invalidateCart()
      setRecipeModal(true)
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
    setPendingShopping(null)
    setShopping(null)
    setAddresses([])
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
    setResult(null)
    setCheckout(null)
    setRecipeModal(false)
    setPlan(null)
    setOrigin(origin)
    setTab('cart')
  }

  async function buildShopping() {
    await run('Buscando produtos', async () => {
      await startShopping(recipeShoppingList(recipe, servings, pantry), 'recipe')
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
    else setRecipeModal(true)
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
          recipe_id: recipe?.source === 'local_demo' ? null : (recipe?.id ?? null),
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
      setResult(null)
    })
  }

  async function switchMerchant(merchantId) {
    await run('Buscando produtos no mercado escolhido', async () => {
      const updated = await api.match(shopping, selectedAddress, merchantId)
      setShopping(updated)
      setResult(null)
    })
  }

  async function skipIngredient(item) {
    await run('Removendo ingrediente da proposta', async () => {
      const updated = await api.skipIngredient(shopping, item.ingredient.id)
      setShopping(updated)
      setResult(null)
    })
  }

  const count = shopping?.items.length ?? 0
  const recipeProps = {
    recipe,
    servings,
    pantry,
    nutrition,
    busy,
    onServings: value => {
      setServings(value)
      setNutrition(null)
      invalidateCart()
    },
    onNutrition:
      recipe?.source === 'local_demo'
        ? undefined
        : () => run('Calculando nutrição', async () => setNutrition(await api.nutrition(recipe.id, servings))),
    onPantry: togglePantry(setPantry),
    onBuild: buildShopping,
  }
  const merchantId = shopping?.items.find(item => item.selected_product)?.selected_product?.merchant_id || null
  return (
    <div className="app-shell">
      <div className="main-shell">
        <header className="topbar">
          <a
            className="brand"
            href="#"
            onClick={event => {
              event.preventDefault()
              setTab('chat')
            }}
            aria-label="iFood Chef, início"
          >
            <span className="brand-icon">
              <Icon name="chef" size={24} />
            </span>
            <b>
              iFood <em>Chef</em>
            </b>
          </a>
          <nav aria-label="Navegação principal">
            {tabs.map(item => (
              <button
                key={item.id}
                className={`nav-item ${tab === item.id ? 'active' : ''}`}
                onClick={() => setTab(item.id)}
                aria-current={tab === item.id ? 'page' : undefined}
              >
                <Icon name={item.icon} size={18} />
                {item.label}
                {item.id === 'cart' && count > 0 && <span className="count">{count}</span>}
              </button>
            ))}
          </nav>
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

          {tab === 'chat' && (
            <section className="workspace">
              <PageHeading title="O que vamos cozinhar?" description="Peça uma receita ou envie seu plano alimentar." />
              <div
                className="chat-panel panel"
                onDragOver={event => event.preventDefault()}
                onDrop={event => {
                  event.preventDefault()
                  if (!busy) selectPdf(event.dataTransfer.files[0])
                }}
              >
                <div className="chat-shortcuts">
                  <button className="button secondary" disabled={!!busy} onClick={() => openRecipe(defaultRecipe)}>
                    <Icon name="book" size={18} />
                    Usar receita de macarrão
                  </button>
                  <span>Macarrão, molho de tomate, creme de leite e carne.</span>
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
                      {item.nutrition && (
                        <small>
                          Nutrição estimada: {item.nutrition.calories_kcal} kcal · {item.nutrition.protein_g} g de
                          proteína · {item.nutrition.carbohydrates_g} g de carboidratos · {item.nutrition.fat_g} g de
                          gorduras ({item.nutrition.basis === 'per_serving' ? 'por porção' : 'receita total'}).
                        </small>
                      )}
                      {item.recipe && (
                        <button className="text-button" disabled={!!busy} onClick={() => openRecipe(item.recipe)}>
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
                      <span className="sr-only">Aguardando resposta…</span>
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
                    placeholder="O que você quer preparar?"
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
                Enter para enviar · Shift + Enter para quebrar a linha · PDF até 10 MB
              </p>
            </section>
          )}

          {tab === 'cart' && (
            <section className="workspace">
              <PageHeading
                title="Minha lista"
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
                  <h2>Sua lista está vazia</h2>
                  <p>Escolha a receita de macarrão ou peça outra na conversa.</p>
                  <button className="button primary" onClick={() => setTab('chat')}>
                    Ir para a conversa
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
                        onSkip={() => skipIngredient(item)}
                      />
                    ))}
                    {shopping.unresolved_ingredients.length > 0 && (
                      <div className="alert info">
                        Há ingredientes que precisam de revisão:{' '}
                        {shopping.unresolved_ingredients.map(item => item.name).join(', ')}. Escolha um produto, defina
                        uma quantidade ou siga sem o ingrediente antes de gerar a proposta.
                      </div>
                    )}
                    {!shopping.items.length && (
                      <div className="alert info">
                        Nenhum ingrediente ficou na proposta. Volte à receita para adicionar itens.
                      </div>
                    )}
                    <button className="text-button" disabled={!!busy} onClick={editIngredients}>
                      Voltar e editar ingredientes
                      <Icon name="arrow" size={17} />
                    </button>
                  </div>
                  <aside className="panel cart-summary">
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
                    {!result && (
                      <>
                        <button
                          className="button primary full"
                          disabled={
                            !!busy ||
                            shopping.status !== 'ready_for_review' ||
                            !!shopping.unresolved_ingredients.length ||
                            !count
                          }
                          onClick={() =>
                            run('Adicionando ao carrinho', async () => {
                              const reviewed = await api.preview(shopping, selectedAddress)
                              const response = await api.apply(reviewed)
                              setResult(response)
                              setCheckout(null)
                            })
                          }
                        >
                          {mockMode ? 'Simular carrinho' : 'Adicionar ao carrinho do iFood'}
                          <Icon name="arrow" size={18} />
                        </button>
                        <p className="subtle small-text">
                          {mockMode
                            ? 'Modo de teste: nenhum carrinho real será criado.'
                            : 'Adiciona os itens revisados. O pedido só é enviado na próxima etapa.'}
                        </p>
                      </>
                    )}
                    {result && (
                      <div className="success" role="status">
                        <Icon name="check" size={26} />
                        <h3>{result.mock_only ? 'Simulação concluída' : 'Carrinho criado'}</h3>
                        <p>{result.message}</p>
                        {result.mock_only ? (
                          <small>Nenhum carrinho real foi alterado.</small>
                        ) : (
                          <>
                            <button
                              className="button primary full"
                              disabled={!!busy || !result.cart_id || !!checkout}
                              onClick={() =>
                                run('Iniciando checkout PIX', async () =>
                                  setCheckout(await api.checkout(result.cart_id)),
                                )
                              }
                            >
                              Enviar pedido e gerar PIX
                              <Icon name="arrow" size={18} />
                            </button>
                            {checkout && (
                              <div className="checkout-result">
                                <p>{checkout.message}</p>
                                {checkout.payment_url && (
                                  <a
                                    className="button secondary full"
                                    href={checkout.payment_url}
                                    target="_blank"
                                    rel="noreferrer"
                                  >
                                    Abrir pagamento PIX
                                    <Icon name="arrow" size={18} />
                                  </a>
                                )}
                                {checkout.pix_qr_code &&
                                (checkout.pix_qr_code.startsWith('https://') ||
                                  checkout.pix_qr_code.startsWith('data:image/')) ? (
                                  <img src={checkout.pix_qr_code} alt="QR Code PIX" />
                                ) : (
                                  checkout.pix_qr_code && <code>{checkout.pix_qr_code}</code>
                                )}
                              </div>
                            )}
                          </>
                        )}
                      </div>
                    )}
                  </aside>
                </div>
              )}
            </section>
          )}
          {recipe && recipeModal && (
            <Modal title={recipe.name} onClose={() => setRecipeModal(false)}>
              <RecipeDetail {...recipeProps} />
            </Modal>
          )}
          {plan && (
            <Modal title="Seu plano alimentar" badge={`${plan.meals.length} refeições`} onClose={() => setPlan(null)}>
              <MealPlanDetail
                plan={plan}
                pantry={planPantry}
                busy={busy}
                onPantry={togglePantry(setPlanPantry)}
                onBuild={buildPlanShopping}
              />
            </Modal>
          )}
        </main>
      </div>
    </div>
  )
}

function PageHeading({ title, description }) {
  return (
    <div className="page-heading">
      <h1>{title}</h1>
      <p>{description}</p>
    </div>
  )
}
