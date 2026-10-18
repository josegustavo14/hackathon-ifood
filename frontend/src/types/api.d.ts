/** Decimal values remain strings in requests and responses, as defined by Pydantic. */
export type Decimal = string
export interface Ingredient {
  id: string
  name: string
  quantity: Decimal
  unit: 'g' | 'kg' | 'ml' | 'l' | 'unit'
  optional: boolean
  notes: string | null
}
export interface Recipe {
  id: string
  name: string
  description: string | null
  servings: number
  ingredients: Ingredient[]
  instructions: string[]
  preparation_time_minutes: number | null
  source: string
  source_url: string | null
}
export interface NutritionFacts {
  calories_kcal: Decimal
  protein_g: Decimal
  carbohydrates_g: Decimal
  fat_g: Decimal
  reference_quantity: Decimal
  reference_unit: string
  basis: 'per_100g' | 'per_unit' | 'per_serving' | 'recipe_total'
  source: string
  estimated: boolean
}
export interface NutritionCalculation {
  recipe_id: string
  servings: number
  status: 'complete' | 'incomplete'
  total: NutritionFacts | null
  per_serving: NutritionFacts | null
  unresolved_ingredients: {
    ingredient_id: string
    name: string
    reason: 'unmapped_ingredient' | 'source_record_unavailable' | 'weight_conversion_unavailable' | 'nutrients_missing'
  }[]
  sources: { ingredient_id: string; fdc_id: number; description: string; grams: Decimal }[]
  warnings: string[]
}
export interface ProductCandidate {
  id: string
  merchant_id: string
  name: string
  description: string | null
  price: Decimal
  currency: 'BRL'
  package_quantity: Decimal | null
  package_unit: string | null
  available: boolean
  image_url: string | null
  source: string
}
export interface ShoppingItem {
  ingredient: Ingredient
  selected_product: ProductCandidate | null
  purchase_quantity: number
  total_price: Decimal
  status: 'pending' | 'matched' | 'unavailable' | 'needs_review'
  reason: string | null
}
export interface ShoppingList {
  id: string
  recipe_id: string | null
  items: ShoppingItem[]
  estimated_subtotal: Decimal
  currency: 'BRL'
  unresolved_ingredients: Ingredient[]
  status: 'pending' | 'ready_for_review' | 'needs_review'
}
export interface CartProposal {
  id: string
  merchant_id: string | null
  address_id: string | null
  items: ShoppingItem[]
  estimated_subtotal: Decimal
  currency: 'BRL'
  requires_confirmation: boolean
  status: 'draft' | 'ready_for_review' | 'confirmed' | 'applied' | 'failed'
}
export interface CartApplyResponse {
  proposal: CartProposal
  mock_only: boolean
  message: string
  cart_id: string | null
  app_deeplink: string | null
}
export interface AgentResponse {
  session_id: string
  message: string
  status: 'completed' | 'needs_input' | 'error'
  recipe: Recipe | null
  shopping_list: ShoppingList | null
  cart_proposal: CartProposal | null
  nutrition: NutritionFacts | null
  nutrition_requested: boolean
}
export interface MealOption {
  name: string
  ingredients: Ingredient[]
}
export interface Meal {
  day: string
  name: string
  frequency_per_week: number
  ingredients: Ingredient[]
  alternative_groups: { options: MealOption[]; choose: number }[]
}
export interface MealPlan {
  id: string
  source_filename: string
  days: string[]
  meals: Meal[]
  extraction_warnings: string[]
  nutrition: NutritionCalculation | null
}
export interface ChefApi {
  health(): Promise<{ status: string; mock_mode: boolean }>
  addresses(): Promise<{ addresses: { address_id: string; alias: string | null; formatted_address: string }[] }>
  searchRecipes(query: string, signal?: AbortSignal): Promise<Recipe[]>
  getRecipe(id: string): Promise<Recipe>
  nutrition(recipe_id: string, servings: number): Promise<NutritionCalculation>
  calculate(recipe_id: string, servings: number): Promise<ShoppingList>
  match(shopping_list: ShoppingList, address_id?: string | null): Promise<ShoppingList>
  preview(shopping_list: ShoppingList, address_id?: string | null): Promise<CartProposal>
  apply(proposal: CartProposal): Promise<CartApplyResponse>
  chat(message: string, session_id: string | null, context: Record<string, unknown>): Promise<AgentResponse>
  parsePlan(file: File): Promise<MealPlan>
}
