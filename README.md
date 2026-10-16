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
5. **Padrões (opcional):** informe um CEP, número, complemento, e-mail e celular padrão para preencher
   as linhas em que a planilha não tem o dado, ou todas as linhas, à escolha do operador (veja abaixo).
6. **Saída:** CSV no modelo + relatório de validação (`.xlsx`) com o número da linha de cada problema.

## Padrões e consulta de CEP

- **CEP padrão:** o app consulta o endereço (rua, bairro, cidade, UF) na API, mostra para conferência e
  permite editar manualmente. Aplica em *somente onde estiver vazio* ou em *todas as linhas*.
- **Número, complemento, e-mail e celular padrão:** mesma lógica de aplicação.
- **CEPs da planilha:** são validados (formato e existência) e, se rua/bairro/cidade/UF estiverem vazios,
  completados pelo CEP. Divergência de cidade/UF e CEP inexistente geram avisos (não reprovam a linha).
- **APIs:** ViaCEP (principal) e BrasilAPI (reserva). Só o CEP é enviado, nunca nome ou CPF.
  Cada CEP distinto é consultado uma vez (com cache) e, se a API cair, as consultas são interrompidas
  após 3 falhas e a geração continua sem elas.

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
| `cep.py` | Consulta de CEP (ViaCEP + BrasilAPI) |
| `test_validators.py`, `test_mapper.py`, `test_cep.py` | Testes (dados fictícios, APIs simuladas) |

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
