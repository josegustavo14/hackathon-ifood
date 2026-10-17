# iFood Chef AI

Agente de IA que transforma receitas e planos alimentares em listas de compras, consultando produtos e preços no iFood e preparando o carrinho automaticamente.

Projeto desenvolvido para o **Hackathon SEMCOMP × iFood 2026**.

## Funcionalidades

- Buscar receitas e extrair seus ingredientes.
- Interpretar planos alimentares enviados em PDF.
- Ajustar quantidades e calcular ingredientes necessários.
- Consultar calorias e macronutrientes.
- Buscar produtos e preços utilizando o MCP do iFood.
- Montar um carrinho de compras para confirmação do usuário.

## Arquitetura

```text
Frontend (React)
       |
       v
Backend (FastAPI)
       |
       +-- Agente IA (LLM)
       |     +-- API de Receitas
       |     +-- Leitor de PDF
       |
       +-- Motor de Compras
       |     +-- Conversão de unidades
       |     +-- Cálculo de quantidades
       |     +-- Seleção de produtos
       |
       +-- Módulo Nutricional
       |     +-- USDA FoodData Central
       |     +-- Open Food Facts
       |
       +-- Cliente MCP
                 |
                 v
             MCP iFood
```

O agente interpreta a solicitação e coordena os serviços. O backend realiza os cálculos e utiliza o MCP do iFood para consultar produtos e gerenciar o carrinho, conforme as ferramentas disponíveis.

## Estrutura de pastas

```text
hackathon-ifood/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/                 # Rotas FastAPI
│   │   ├── models/              # Schemas compartilhados
│   │   ├── agent/               # Agente LLM
│   │   ├── integrations/
│   │   │   ├── ifood/           # Cliente MCP iFood
│   │   │   └── recipes/         # API de receitas
│   │   ├── shopping/            # Motor de compras
│   │   └── nutrition/           # Calorias e macros
│   ├── tests/
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── components/          # Componentes React
│   │   ├── pages/               # Telas
│   │   ├── services/            # Comunicação com backend
│   │   └── App.jsx
│   └── package.json
│
├── docs/                        # Documentação e diagramas
├── .env.example                 # Variáveis de ambiente
└── README.md
```

## Equipe

| Integrante | Responsabilidade | Diretórios principais |
|---|---|---|
| **Leffeck** | Integração MCP iFood, busca de produtos e carrinho | `integrations/ifood/` |
| **Julia** | Agente IA, API de receitas e leitura de PDF | `agent/`, `integrations/recipes/` |
| **José** | Motor de compras, nutrição e contratos de dados | `shopping/`, `nutrition/`, `models/` |
| **Diego** | Interface React, chat, upload e experiência do usuário | `frontend/` |

## Tecnologias

- **Frontend:** React
- **Backend:** Python + FastAPI
- **IA:** LLM com chamadas de ferramentas
- **Integração iFood:** Model Context Protocol (MCP)
- **Receitas:** [API Receitas](https://github.com/DenilsonRabelo/API-receitas)
- **Nutrição:** USDA FoodData Central e Open Food Facts

## Fluxo principal

1. Usuário solicita uma receita ou envia um plano alimentar.
2. O agente identifica os ingredientes necessários.
3. O backend calcula quantidades e informações nutricionais.
4. O MCP do iFood é utilizado para buscar produtos e preços.
5. O sistema prepara o carrinho para revisão e confirmação do usuário.

---

**SEMCOMP × iFood 2026** — Da receita ao carrinho.