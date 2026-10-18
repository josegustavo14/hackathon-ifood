export const defaultRecipe = {
  id: 'demo-macarrao-cremoso',
  name: 'Macarrão com carne e molho cremoso',
  description: 'Receita de exemplo para 4 pessoas.',
  servings: 4,
  source: 'local_demo',
  preparation_time_minutes: 25,
  ingredients: [
    { id: 'pasta', name: 'Macarrão', quantity: '500', unit: 'g' },
    { id: 'tomato-sauce', name: 'Molho de tomate', quantity: '300', unit: 'g' },
    { id: 'cream', name: 'Creme de leite', quantity: '200', unit: 'g' },
    { id: 'beef', name: 'Carne moída', quantity: '500', unit: 'g' },
  ],
  instructions: [
    'Cozinhe o macarrão em água e escorra.',
    'Refogue a carne até dourar e cozinhar por completo.',
    'Adicione o molho de tomate e deixe cozinhar por 5 minutos.',
    'Misture o creme de leite e o macarrão. Aqueça e sirva.',
  ],
}
