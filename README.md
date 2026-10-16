# Seguro Viagem — Planilha → Modelo de emissão

Aplicação em Python/Streamlit que lê uma planilha de passageiros (`.xlsx`, `.xls` ou `.csv`), **detecta
automaticamente onde está cada campo**, valida **nome, CPF e data de nascimento** e gera o CSV no formato do
modelo `emissao_planilha_modelo`.

O app abre numa **página inicial** para escolher a ação:

- **Planilha de emissão de seguro viagem** (descrita abaixo);
- **Separador e renomeador de vouchers GTA** (descrito na seção seguinte).

## Planilha de emissão: como funciona

1. **Estrutura:** encontra a linha do cabeçalho (mesmo com títulos acima da tabela) e a aba mais adequada.
2. **Mapeamento:** associa cada campo do modelo a uma coluna da planilha pelo nome do cabeçalho
   (ex.: "E-mail técnico" → E-mail) e pelo conteúdo (parece CPF, data, e-mail, celular, CEP, UF).
   Funciona até sem cabeçalho. Você revisa e ajusta antes de gerar.
3. **Conversão:** grava no padrão do modelo (separador `;`, quebra de linha CRLF):
   data `DD/MM/AAAA`, celular `00-000000000`, CEP `00000-000`, CPF no formato escolhido.
   Todo o texto sai **sem acentos e caracteres especiais** (São Paulo → Sao Paulo, Paraná → Parana).
   O **sexo** sai somente como `M` ou `F` (Masculino, Masc, Homem, Male → M; Feminino, Fem, Mulher, Female → F);
   valor não reconhecido sai em branco e gera aviso.
4. **Validação:** nome (nome e sobrenome, sem números), CPF (dígitos verificadores, repetidos, duplicados)
   e data de nascimento (existente, não futura, idade máxima). E-mail, celular, CEP e UF geram apenas avisos.
5. **Padrões (opcional):** informe um CEP, número, complemento, e-mail e celular padrão para preencher
   as linhas em que a planilha não tem o dado, ou todas as linhas, à escolha do operador (veja abaixo).
6. **Saída:** o CSV no modelo leva **somente as linhas válidas**. Quem tem nome, CPF ou data incorretos
   vai para as **pendências do cliente** (planilha `.xlsx` + mensagem pronta), com o dado errado, o motivo
   e como corrigir. Há também um relatório de validação interno com o número da linha de cada problema.

## Separador e renomeador de vouchers GTA

Aceita um ou vários PDFs de vouchers GTA e devolve um PDF por voucher, nomeado assim:

```
NOME_INICIOaFIM_PLANO.pdf
FABIO GARCIA_22.11.26a30.11.26_10487-NACIONAL 30.000.pdf
```

- **Separação:** cada voucher começa na página "Voucher de assistência de viagem" (traz *Voucher: nº* e *Nome:*);
  as páginas seguintes (bilhete, encarte de benefícios) ficam com ele. Um PDF com vários vouchers é separado
  automaticamente; um PDF de um voucher só é devolvido intacto, apenas com o nome novo.
- **Datas:** DD/MM/AAAA vira DD.MM.AA, com "a" entre o início e o fim da vigência.
- **Conferência:** os dados lidos aparecem numa tabela editável. Campo não encontrado ou data inválida bloqueia
  o voucher até ser corrigido na tabela; voucher repetido vem desmarcado; nomes iguais ganham ` (2)`.
- **Acentos:** removidos do nome do arquivo por padrão (opção na tela). Caracteres proibidos em nomes de arquivo
  viram `-`.
- **Download:** um voucher vira PDF direto; vários viram um `.zip`.
- Lê apenas PDFs com texto (não faz OCR de imagem).

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
| `app.py` | Roteador: página inicial e navegação |
| `paginas/inicio.py` | Página inicial (escolha da ação) |
| `paginas/emissao_seguro.py` | Página da planilha de emissão |
| `paginas/vouchers.py` | Página do separador/renomeador de vouchers |
| `vouchers.py` | Leitura, separação e nome dos vouchers GTA |
| `mapper.py` | Detecção de colunas e conversão para o modelo |
| `validators.py` | Regras de validação de nome, CPF e data |
| `cep.py` | Consulta de CEP (ViaCEP + BrasilAPI) |
| `test_validators.py`, `test_mapper.py`, `test_cep.py`, `test_vouchers.py` | Testes (dados fictícios, APIs simuladas) |

## Testes

```bash
pip install pytest
pytest
```

## Atenção: dados pessoais (LGPD)

A planilha contém CPF, nome e data de nascimento. Por isso:

- **Não** versione planilhas nem vouchers reais (`.gitignore` já ignora `.xlsx`, `.xls`, `.csv`, `.pdf` e `.zip`).
- Ao publicar o app (ex.: Streamlit Community Cloud), restrinja o acesso, pois os arquivos enviados são
  processados no servidor da hospedagem.
- A validação é **local** (formato e dígitos verificadores). Ela não confirma na Receita Federal que o CPF
  pertence àquele nome e data de nascimento.
