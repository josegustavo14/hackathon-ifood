import React, { useEffect, useRef, useState } from 'react'
import { api } from './services/api'
import Icon from './components/Icon'
import NutritionPanel from './components/NutritionPanel'
import RecipeArt from './components/RecipeArt'
import { amount, excludePantry, money, quantity, validatePdf } from './utils'
import './styles.css'

const tabs = [
  { id: 'recipes', label: 'Receitas', icon: 'book' },
  { id: 'chat', label: 'Chef assistente', icon: 'chat' },
  { id: 'plan', label: 'Plano alimentar', icon: 'file' },
  { id: 'cart', label: 'Minha lista', icon: 'bag' },
]

export default function App() {
  const [tab, setTab] = useState('recipes')
  const [query, setQuery] = useState('lasanha')
  const [recipes, setRecipes] = useState([])
  const [searched, setSearched] = useState(false)
  const [recipe, setRecipe] = useState(null)
  const [servings, setServings] = useState(4)
  const [pantry, setPantry] = useState([])
  const [nutrition, setNutrition] = useState(null)
  const [shopping, setShopping] = useState(null)
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
  const [plan, setPlan] = useState(null)
  const [pdf, setPdf] = useState(null)
  const [pdfUrl, setPdfUrl] = useState('')
  const fileInput = useRef(null)
  const chatEnd = useRef(null)
  const recipeDetail = useRef(null)
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
    if (!pdf) {
      setPdfUrl('')
      return
    }
    const url = URL.createObjectURL(pdf)
    setPdfUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [pdf])

  useEffect(() => {
    if (tab === 'chat') chatEnd.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [messages, tab])

  useEffect(() => {
    if (recipe && tab === 'recipes') recipeDetail.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [recipe, tab])

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
    setProposal(null)
    setConfirmed(false)
    setResult(null)
  }

  async function openRecipe(value) {
    await run('Carregando receita', async () => {
      const data = typeof value === 'object' ? value : await api.getRecipe(value)
      setRecipe(data)
      setServings(data.servings)
      setPantry([])
      setNutrition(null)
      invalidateCart()
      setTab('recipes')
      if (data.source !== 'llm_web') setNutrition(await api.nutrition(data.id, data.servings))
    })
  }

  async function buildShopping() {
    await run('Calculando ingredientes e produtos', async () => {
      const list = excludePantry(await api.calculate(recipe.id, servings), pantry)
      if (!list.items.length)
        throw new Error('Você já tem todos os ingredientes! Desmarque algum item para gerar uma lista de compras.')
      const matched = await api.match(list)
      setShopping(matched)
      setProposal(null)
      setResult(null)
      setConfirmed(false)
      setTab('cart')
    })
  }

  async function sendChat(event) {
    event.preventDefault()
    const text = message.trim()
    if (!text) return
    await run('O Chef está respondendo', async () => {
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
          { role: 'assistant', text: response.message, recipe: response.recipe, status: response.status },
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
    setPlan(null)
  }

  const count = shopping?.items.length ?? 0
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
            <span className="status-dot" /> Modo demonstrativo
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
          {busy && (
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

              {recipe && (
                <section ref={recipeDetail} className="panel recipe-detail">
                  <div className="section-heading">
                    <div>
                      <span className="eyebrow muted">MÃO NA MASSA</span>
                      <h2>{recipe.name}</h2>
                    </div>
                    <span className="pill">
                      {recipe.source === 'mock_ep00' ? 'Receita demonstrativa' : recipe.source}
                    </span>
                  </div>
                  <p className="subtle">{recipe.description}</p>
                  <div className="detail-grid">
                    <div>
                      <div className="ingredient-heading">
                        <h3>Ingredientes</h3>
                        <label className="servings">
                          Porções{' '}
                          <input
                            type="number"
                            min="1"
                            max="100"
                            step="1"
                            value={servings}
                            disabled={!!busy}
                            onChange={event => {
                              const value = event.target.value
                              setServings(value === '' ? '' : Number(value))
                              invalidateCart()
                            }}
                          />
                        </label>
                      </div>
                      <p className="subtle small-text">Marque “já tenho” para retirar um ingrediente da compra.</p>
                      <ul className="ingredient-list">
                        {recipe.ingredients.map(item => (
                          <li key={item.id}>
                            <span>
                              <strong>{item.name}</strong>
                              <small>
                                {amount((Number(item.quantity) * Number(servings || 0)) / recipe.servings)}{' '}
                                {item.unit === 'unit' ? 'un.' : item.unit}
                                {item.optional ? ' · opcional' : ''}
                                {item.notes ? ` · ${item.notes}` : ''}
                              </small>
                            </span>
                            <label className="pantry">
                              <input
                                type="checkbox"
                                checked={pantry.includes(item.id)}
                                disabled={!!busy}
                                onChange={() => {
                                  setPantry(prev =>
                                    prev.includes(item.id) ? prev.filter(id => id !== item.id) : [...prev, item.id],
                                  )
                                  invalidateCart()
                                }}
                              />
                              Já tenho
                            </label>
                          </li>
                        ))}
                      </ul>
                      <button
                        className="button primary full"
                        disabled={
                          !!busy ||
                          !Number.isInteger(servings) ||
                          servings < 1 ||
                          servings > 100 ||
                          pantry.length === recipe.ingredients.length
                        }
                        onClick={buildShopping}
                      >
                        <Icon name="bag" size={18} />
                        Montar minha lista de compras
                        <Icon name="arrow" size={18} />
                      </button>
                    </div>
                    <div>
                      <h3>Modo de preparo</h3>
                      <ol className="instructions">
                        {recipe.instructions.map((step, index) => (
                          <li key={index}>
                            <span>{index + 1}</span>
                            <p>{step}</p>
                          </li>
                        ))}
                      </ol>
                      {nutrition && <NutritionPanel calculation={nutrition} />}
                    </div>
                  </div>
                </section>
              )}
            </>
          )}

          {tab === 'chat' && (
            <section className="workspace">
              <PageHeading
                eyebrow="UMA AJUDA NA COZINHA"
                title="Converse com o Chef"
                description="Conte o que você quer preparar e planeje sua próxima refeição."
              />
              <div className="chat-panel panel">
                <div className="chat-title">
                  <span className="brand-icon">
                    <Icon name="chef" />
                  </span>
                  <div>
                    <strong>Chef assistente</strong>
                    <small>Respostas demonstrativas nesta etapa</small>
                  </div>
                  <span className="pill">AI</span>
                </div>
                <div className="messages" aria-live="polite" aria-label="Conversa com o Chef">
                  {messages.map((item, index) => (
                    <div key={index} className={`message ${item.role}`}>
                      <span className="message-author">{item.role === 'user' ? 'Você' : 'Chef'}</span>
                      <p>{item.text}</p>
                      {item.status === 'needs_input' && (
                        <small>O agente precisa de mais informações ou de uma próxima etapa.</small>
                      )}
                      {item.status === 'error' && (
                        <small role="alert">O agente não conseguiu concluir a solicitação.</small>
                      )}
                      {item.recipe && (
                        <button className="text-button" disabled={!!busy} onClick={() => openRecipe(item.recipe.id)}>
                          Abrir {item.recipe.name}
                          <Icon name="arrow" size={16} />
                        </button>
                      )}
                    </div>
                  ))}
                  <div ref={chatEnd} />
                </div>
                <form className="chat-form" onSubmit={sendChat}>
                  <label className="sr-only" htmlFor="chat-message">
                    Mensagem para o Chef
                  </label>
                  <textarea
                    id="chat-message"
                    placeholder="Ex.: Quero fazer lasanha para quatro pessoas…"
                    rows="2"
                    maxLength={4000}
                    value={message}
                    disabled={!!busy}
                    onChange={event => setMessage(event.target.value)}
                    onKeyDown={event => {
                      if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
                        event.preventDefault()
                        if (!busy && message.trim()) event.currentTarget.form.requestSubmit()
                      }
                    }}
                  />
                  <button className="button primary" disabled={!!busy || !message.trim()}>
                    Enviar
                    <Icon name="arrow" size={18} />
                  </button>
                </form>
              </div>
              <p className="footnote">
                O agente desta versão responde com um exemplo fixo. Para calcular compras, escolha uma receita na aba
                Receitas.
              </p>
            </section>
          )}

          {tab === 'plan' && (
            <section className="workspace">
              <PageHeading
                eyebrow="SUA ROTINA, MAIS LEVE"
                title="Seu plano alimentar"
                description="Envie o PDF e consulte as refeições, os ingredientes e as alternativas do plano."
              />
              <div
                className="upload-zone"
                onDragOver={event => event.preventDefault()}
                onDrop={event => {
                  event.preventDefault()
                  if (!busy) selectPdf(event.dataTransfer.files[0])
                }}
              >
                <span className="upload-icon">
                  <Icon name="upload" size={30} />
                </span>
                <h3>{pdf ? pdf.name : 'Seu planejamento começa aqui'}</h3>
                <p>
                  Arraste seu PDF para esta área ou escolha um arquivo.
                  <br />
                  PDF de até 10 MiB.
                </p>
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
                <button className="button secondary" disabled={!!busy} onClick={() => fileInput.current.click()}>
                  Selecionar PDF
                </button>
                {pdf && (
                  <button
                    className="button primary"
                    disabled={!!busy}
                    onClick={() => run('Enviando plano alimentar', async () => setPlan(await api.parsePlan(pdf)))}
                  >
                    Enviar e visualizar plano
                    <Icon name="arrow" size={18} />
                  </button>
                )}
              </div>
              <div className="alert info">
                A API extrai e interpreta o texto do PDF. Confira as refeições e os avisos de extração: o plano ainda
                não gera compras automaticamente.
              </div>
              {pdfUrl && (
                <details className="panel pdf-preview">
                  <summary>Visualizar o PDF selecionado</summary>
                  <object data={pdfUrl} type="application/pdf" aria-label="Visualização do PDF selecionado">
                    <p>
                      Seu navegador não exibe PDFs aqui.{' '}
                      <a href={pdfUrl} target="_blank" rel="noreferrer">
                        Abrir PDF em outra aba
                      </a>
                      .
                    </p>
                  </object>
                  <a href={pdfUrl} target="_blank" rel="noreferrer">
                    Abrir PDF em outra aba
                  </a>
                </details>
              )}
              {plan && (
                <section className="panel">
                  <div className="section-heading">
                    <div>
                      <span className="eyebrow muted">PLANO RETORNADO PELA API</span>
                      <h2>Refeições da semana</h2>
                    </div>
                    <span className="pill">{plan.days.length} dias</span>
                  </div>
                  <p className="subtle">Arquivo: {plan.source_filename}</p>
                  {plan.extraction_warnings.map((warning, index) => (
                    <div className="alert info" key={index}>
                      {warning}
                    </div>
                  ))}
                  <div className="meal-grid">
                    {plan.meals.map((meal, index) => (
                      <article className="meal-card" key={index}>
                        <span className="eyebrow muted">{meal.day}</span>
                        <h3>{meal.name}</h3>
                        <ul>
                          {meal.ingredients.map(ingredient => (
                            <li key={ingredient.id}>
                              {ingredient.name} <span>{quantity(ingredient)}</span>
                            </li>
                          ))}
                        </ul>
                        {meal.alternative_groups?.map((group, groupIndex) => (
                          <div className="alternatives" key={groupIndex}>
                            <strong>Escolher {group.choose} alternativa(s)</strong>
                            {group.options.map((option, optionIndex) => (
                              <p key={optionIndex}>
                                {option.name}:{' '}
                                {option.ingredients
                                  .map(ingredient => `${ingredient.name} (${quantity(ingredient)})`)
                                  .join(', ')}
                              </p>
                            ))}
                          </div>
                        ))}
                      </article>
                    ))}
                  </div>
                  <p className="footnote">
                    As alternativas são opções: não são somadas como compras obrigatórias. O cálculo por plano depende
                    de uma próxima versão da API.
                  </p>
                </section>
              )}
            </section>
          )}

          {tab === 'cart' && (
            <section className="workspace">
              <PageHeading
                eyebrow="DA RECEITA PARA O MERCADO"
                title="Sua lista, bem pensada"
                description="Confira as quantidades, os produtos e o subtotal antes de confirmar."
              />
              {!shopping ? (
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
                      <article className="cart-item" key={item.ingredient.id}>
                        <span className="product-icon">
                          <Icon name="bag" size={22} />
                        </span>
                        <div>
                          <h3>{item.selected_product?.name || item.ingredient.name}</h3>
                          <p>
                            Receita: {quantity(item.ingredient)} de {item.ingredient.name}
                          </p>
                          {item.selected_product ? (
                            <small>
                              {item.purchase_quantity} embalagem(ns) · {money(item.selected_product.price)} cada
                            </small>
                          ) : (
                            <small className="warning-text">Produto não encontrado · precisa de revisão</small>
                          )}
                        </div>
                        <strong>{money(item.total_price)}</strong>
                      </article>
                    ))}
                    {shopping.unresolved_ingredients.length > 0 && (
                      <div className="alert info">
                        Há ingredientes sem produto disponível:{' '}
                        {shopping.unresolved_ingredients.map(item => item.name).join(', ')}. Revise os ingredientes na
                        receita antes de gerar a proposta.
                      </div>
                    )}
                    <button className="text-button" disabled={!!busy} onClick={() => setTab('recipes')}>
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
                      Preços fictícios em BRL. Frete e outras taxas não estão incluídos.
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
                            setProposal(await api.preview(shopping))
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
                        <small>A aplicação nesta etapa é apenas simulada.</small>
                      </div>
                    )}
                    {result && (
                      <div className="success" role="status">
                        <Icon name="check" size={26} />
                        <h3>{result.mock_only ? 'Simulação concluída!' : 'Proposta processada'}</h3>
                        <p>{result.message}</p>
                        {result.mock_only && <small>Nenhum carrinho real foi alterado.</small>}
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
          <footer className="page-footer">
            <span className="footer-brand">
              iFood <em>Chef AI</em>
            </span>
            <span>Receitas, produtos e preços demonstrativos</span>
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
