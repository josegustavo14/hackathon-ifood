import React, { useState } from 'react'
import { amount } from '../utils'

const macros = [
  ['calories_kcal', 'kcal', 'Calorias'],
  ['protein_g', 'g', 'Proteínas'],
  ['carbohydrates_g', 'g', 'Carboidratos'],
  ['fat_g', 'g', 'Gorduras'],
]
const additional = [
  ['fiber_g', 'g', 'Fibras'],
  ['sugars_g', 'g', 'Açúcares'],
  ['saturated_fat_g', 'g', 'Gorduras saturadas'],
  ['sodium_mg', 'mg', 'Sódio'],
]
const reasons = {
  unmapped_ingredient: 'Sem correspondência USDA validada',
  source_record_unavailable: 'Registro USDA indisponível',
  weight_conversion_unavailable: 'Falta um peso confiável em gramas',
  nutrients_missing: 'Registro sem todos os macronutrientes',
}

export default function NutritionPanel({ calculation, showPortions = true, totalLabel = 'Receita inteira' }) {
  const [basis, setBasis] = useState('per_serving')
  if (!calculation) return null
  const canDivide = showPortions && !!calculation.per_serving
  const selected = canDivide && basis === 'per_serving' ? 'per_serving' : 'total'
  const facts = calculation.status === 'complete' ? calculation[selected] : null
  const sources = calculation.sources ?? []

  return (
    <section className="nutrition" aria-label="Informação nutricional">
      <h3>Informação nutricional</h3>
      {facts ? (
        <>
          {canDivide && (
            <div className="nutrition-tabs" role="group" aria-label="Base do cálculo nutricional">
              <button type="button" aria-pressed={selected === 'per_serving'} onClick={() => setBasis('per_serving')}>
                Por porção
              </button>
              <button type="button" aria-pressed={selected === 'total'} onClick={() => setBasis('total')}>
                {totalLabel}
              </button>
            </div>
          )}
          <p>
            {selected === 'per_serving' ? `por porção · ${calculation.servings ?? 1} porções na receita` : totalLabel}
          </p>
          <div className="nutrition-values">
            {macros.map(([key, unit, label]) => (
              <div key={key}>
                <strong>
                  {amount(facts[key])}
                  <small> {unit}</small>
                </strong>
                <span>{label}</span>
              </div>
            ))}
          </div>
          <dl className="nutrition-additional">
            {additional
              .filter(([key]) => facts[key] != null)
              .map(([key, unit, label]) => (
                <div key={key}>
                  <dt>{label}</dt>
                  <dd>
                    {amount(facts[key])} {unit}
                  </dd>
                </div>
              ))}
          </dl>
          <small>
            {facts.estimated ? 'Valores estimados' : 'Valores informados'} ·{' '}
            {facts.source === 'mock_ep00' ? 'Dados demonstrativos' : facts.source}
          </small>
        </>
      ) : (
        <>
          <p>Não foi possível calcular os totais com todos os ingredientes.</p>
          <ul className="nutrition-unresolved">
            {calculation.unresolved_ingredients?.map(item => (
              <li key={item.ingredient_id ?? item.name}>
                {item.name}: {reasons[item.reason] ?? 'Dados indisponíveis'}.
              </li>
            ))}
          </ul>
        </>
      )}
      {sources.length > 0 && (
        <details className="nutrition-sources">
          <summary>Ingredientes e fontes ({sources.length})</summary>
          <p>
            Quantidades e nutrientes do total calculado.{' '}
            {facts ? '' : 'Dados parciais; não representam o total da receita.'}
          </p>
          <div className="nutrition-table">
            <table>
              <thead>
                <tr>
                  <th>Ingrediente</th>
                  <th>Peso</th>
                  <th>kcal</th>
                  <th>Proteínas</th>
                  <th>Carboidratos</th>
                  <th>Gorduras</th>
                </tr>
              </thead>
              <tbody>
                {sources.map(source => (
                  <tr key={source.ingredient_id}>
                    <th scope="row">
                      <a
                        href={`https://fdc.nal.usda.gov/food-details/${source.fdc_id}/nutrients`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {source.name ?? source.description}
                      </a>
                    </th>
                    <td>{amount(source.grams)} g</td>
                    {macros.map(([key, unit]) => (
                      <td key={key}>
                        {source.nutrients?.[key] == null
                          ? '—'
                          : `${amount(source.nutrients[key])}${unit === 'g' ? ' g' : ''}`}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
      {calculation.warnings?.map((warning, index) => (
        <p className="subtle small-text" key={index}>
          {warning}
        </p>
      ))}
    </section>
  )
}
