import React from 'react'
import { amount } from '../utils'

export default function NutritionPanel({ calculation }) {
  if (!calculation) return null

  const facts = calculation.status === 'complete' ? calculation.per_serving : null

  return <div className="nutrition">
    <h3>Um olhar para a nutrição</h3>
    {facts ? <>
      <p>por porção · referência: {amount(facts.reference_quantity)} {facts.reference_unit === 'serving' ? 'porção' : facts.reference_unit}</p>
      <div className="nutrition-values">{[['calories_kcal', 'kcal', 'Calorias'], ['protein_g', 'g', 'Proteínas'], ['carbohydrates_g', 'g', 'Carboidratos'], ['fat_g', 'g', 'Gorduras']].map(([key, unit, label]) => <div key={key}><strong>{amount(facts[key])}<small> {unit}</small></strong><span>{label}</span></div>)}</div>
      <small>{facts.estimated ? 'Valores estimados' : 'Valores informados'} · {facts.source === 'mock_ep00' ? 'Dados demonstrativos' : facts.source}</small>
    </> : <>
      <p>Não foi possível calcular os totais desta receita com os dados disponíveis.</p>
      {calculation.unresolved_ingredients?.length > 0 && <p>Ingredientes sem dados: {calculation.unresolved_ingredients.map(item => item.name).join(', ')}.</p>}
    </>}
    {calculation.warnings?.map((warning, index) => <p className="subtle small-text" key={index}>{warning}</p>)}
  </div>
}
