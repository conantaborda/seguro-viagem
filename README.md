# Seguro Viagem — Planilha → Modelo de emissão

Aplicação em Python/Streamlit que lê uma planilha de passageiros (`.xlsx`, `.xls` ou `.csv`), **detecta
automaticamente onde está cada campo**, valida **nome, CPF e data de nascimento** e gera o CSV no formato do
modelo `emissao_planilha_modelo`.

## Como funciona

1. **Estrutura:** encontra a linha do cabeçalho (mesmo com títulos acima da tabela) e a aba mais adequada.
2. **Mapeamento:** associa cada campo do modelo a uma coluna da planilha pelo nome do cabeçalho
   (ex.: "E-mail técnico" → E-mail) e pelo conteúdo (parece CPF, data, e-mail, celular, CEP, UF).
   Funciona até sem cabeçalho. Você revisa e ajusta antes de gerar.
3. **Conversão:** grava no padrão do modelo (separador `;`, quebra de linha CRLF):
   data `DD/MM/AAAA`, celular `00-000000000`, CEP `00000-000`, CPF no formato escolhido.
4. **Validação:** nome (nome e sobrenome, sem números), CPF (dígitos verificadores, repetidos, duplicados)
   e data de nascimento (existente, não futura, idade máxima). E-mail, celular, CEP e UF geram apenas avisos.
5. **Saída:** CSV no modelo + relatório de validação (`.xlsx`) com o número da linha de cada problema.

## Executar

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Estrutura

| Arquivo | Função |
|---|---|
| `app.py` | Interface Streamlit |
| `mapper.py` | Detecção de colunas e conversão para o modelo |
| `validators.py` | Regras de validação de nome, CPF e data |
| `test_validators.py`, `test_mapper.py` | Testes (dados fictícios) |

## Testes

```bash
pip install pytest
pytest
```

## Atenção: dados pessoais (LGPD)

A planilha contém CPF, nome e data de nascimento. Por isso:

- **Não** versione planilhas reais (`.gitignore` já ignora `.xlsx`, `.xls` e `.csv`).
- Ao publicar o app (ex.: Streamlit Community Cloud), restrinja o acesso, pois os arquivos enviados são
  processados no servidor da hospedagem.
- A validação é **local** (formato e dígitos verificadores). Ela não confirma na Receita Federal que o CPF
  pertence àquele nome e data de nascimento.
