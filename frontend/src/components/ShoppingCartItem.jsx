import React, { useState } from 'react'
import Icon from './Icon'
import { money, multiplyMoney, quantity } from '../utils'

function unresolvedMessage(item) {
  if (item.reason === 'choose_alternative') return 'Escolha uma das alternativas da receita.'
  if (item.reason === 'unit_conversion_not_verified') return 'O catálogo usa outra medida; escolha quantas embalagens deseja.'
  if (item.reason === 'package_quantity_unknown') return 'O catálogo não informa o tamanho; escolha quantos itens deseja.'
  return 'Produto não encontrado · precisa de revisão'
}

export default function ShoppingCartItem({ item, merchantId, busy, onSelect, onSwitchMerchant }) {
  const [productId, setProductId] = useState('')
  const [packages, setPackages] = useState(1)
  const suggestions = item.suggested_products || []
  const chosen = suggestions.find(product => product.id === productId)
  const otherMerchant = !!chosen && !!merchantId && chosen.merchant_id !== merchantId
  const validCount = Number.isInteger(packages) && packages >= 1 && packages <= 99

  return <article className="cart-item" key={item.ingredient.id}>
    <span className="product-icon"><Icon name="bag" size={22}/></span>
    <div>
      <h3>{item.selected_product?.name || item.ingredient.name}</h3>
      <p>Receita: {quantity(item.ingredient)} de {item.ingredient.name}</p>
      {item.selected_product
        ? <><small>{item.purchase_quantity} embalagem(ns) · {money(item.selected_product.price)} cada</small>
          {item.reason === 'manually_selected_unverified_quantity' && <small className="warning-text manual-note">Quantidade escolhida por você; equivalência com a receita não verificada.</small>}</>
        : <>
          <small className="warning-text">{unresolvedMessage(item)}</small>
          {suggestions.length > 0 && <div className="manual-picker">
            <label>Produto encontrado
              <select aria-label={`Produto para ${item.ingredient.name}`} value={productId} onChange={event => setProductId(event.target.value)} disabled={!!busy}>
                <option value="">Escolha um produto</option>
                {suggestions.map(product => <option key={`${product.merchant_id}:${product.id}`} value={product.id}>
                  {product.name} · {money(product.price)} · {product.merchant_name || `Mercado ${product.merchant_id.slice(0, 8)}`}
                </option>)}
              </select>
            </label>
            {merchantId && !suggestions.some(product => product.merchant_id === merchantId) && <small className="warning-text">Nenhuma opção deste ingrediente no mercado dos itens já selecionados.</small>}
            <label>Quantidade de produtos
              <input aria-label={`Quantidade de produtos para ${item.ingredient.name}`} type="number" min="1" max="99" step="1" value={packages} onChange={event => setPackages(Number(event.target.value))} disabled={!!busy}/>
            </label>
            {chosen && validCount && <small>Preço estimado: {money(multiplyMoney(chosen.price, packages))}. {chosen.package_quantity ? `Embalagem: ${chosen.package_quantity} ${chosen.package_unit}.` : 'Tamanho não informado pelo catálogo.'}</small>}
            {otherMerchant
              ? <button className="button primary" disabled={!!busy} onClick={() => onSwitchMerchant(chosen.merchant_id)}>Buscar tudo neste mercado</button>
              : <button className="button primary" disabled={!!busy || !chosen || !validCount} onClick={() => onSelect(chosen.id, packages)}>Adicionar à proposta</button>}
            {otherMerchant && <small>Trocar de mercado refaz a lista e remove escolhas manuais anteriores.</small>}
            <small>A quantidade escolhida é de produtos do catálogo; o peso necessário da receita não foi convertido.</small>
          </div>}
        </>}
    </div>
    <strong>{money(item.total_price)}</strong>
  </article>
}
