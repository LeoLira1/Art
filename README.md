# Descanso de tela — CAMDA

Rede minimalista de nós e fios em tela cheia (fundo off-white, bolinhas pretas
com sombra suave, linhas finas). **Nenhum texto na tela**: a informação só
aparece no tooltip ao passar o mouse num nó, ou ao tocar nele no celular/tablet.

| Nó | Significado |
|---|---|
| ● preto sólido | falta (divergência aberta) |
| ○ vazado | sobra |
| ● vermelho com onda | tarefa urgente (Risca) |
| ● amarelo | tarefa normal |
| ● verde | tarefa "quando der" |
| · pontinhos | decoração: `round(itens reais × 0,8)` (divergências + tarefas pendentes) |

O tamanho da falta/sobra cresce com a raiz da quantidade física
(`4 + √|qtd| × 3,2`, escalado pelo menor lado da tela ÷ 900).

Fios de relação ligam divergências do mesmo produto (com ou sem prefixo `US`)
ou do mesmo cooperado (FALTANDO, SOBRANDO e Invertido não contam). Cada nó liga
só às **2 mais próximas** do mesmo grupo, na posição atual, recalculado a cada
~2 s com fade (opacidade 0,35). Mouse em cima de um nó (ou toque) acende o
grupo dele inteiro, conectado, a 0,9 e apaga o resto para 0,15.

Quando o número de itens muda na recarga, a cena não é recriada: nós resolvidos
e a poeira que sobra encolhem e somem (~1,5 s); os novos nascem pequenos e
crescem. Sem nenhuma divergência nem tarefa, a tela fica só com o fundo liso.

Toque no vazio liga/desliga a tela cheia.

## Busca

Barra de vidro fosco no canto inferior direito (fica meio apagada até passar o
mouse; `/` ou `Ctrl+K` foca). Busca cooperado, produto (nome ou código, com ou
sem `US`) e tarefa, com autocompletar. Ignora acento e maiúscula, tolera erro de
digitação e apelido (`serginho` → SERGIO). Enquanto digita, o que casa já se
destaca; ao escolher uma sugestão (clique, Enter ou Tab), ficam só as
divergências daquele cooperado/produto: crescem um pouco, ganham anel e um
cacho de fios próprio, e o resto apaga. A escolha sobrevive às recargas de
dados. `Esc` ou `×` limpa.

## Rodar

```bash
pip install -r requirements.txt
streamlit run app.py
```

Credenciais em `.streamlit/secrets.toml` (as mesmas do CAMDA Estoque; o arquivo
é ignorado pelo git):

```toml
TURSO_DATABASE_URL = "libsql://..."
TURSO_AUTH_TOKEN = "..."
```

Lê só duas tabelas, apenas leitura: `divergencias` (abertas) e `tarefas`
(`feita = 0`). Recarrega a cada 5 minutos, com cache compartilhado entre telas
abertas (uma leitura por intervalo, ~110 linhas). Se o banco falhar, mantém a
última leitura boa e registra `falha ao ler o Turso (mostrando dados de N min
atrás)` no log a cada recarga.

**Pulso:** cada recarga do fragmento grava a hora (`data-t`) nos blocos de
dados. Se o pulso parar por mais de 3 intervalos + 1 min (~16 min), o websocket
com o servidor morreu (app hibernou no Streamlit Cloud, rede caiu) e o canvas
recarrega a página sozinho, em vez de animar dados velhos para sempre.
`__descanso()` mostra `pulsoHa_s` (segundos desde o último pulso) e
`dadosDe_min` (idade da última leitura boa do banco).

## Como funciona

- `descanso.html`: canvas em HTML/JS puro, embutido com
  `st.components.v1.html`. O HTML **nunca muda**, então o iframe nunca é
  recriado.
- Os dados vão para a página num bloco escondido, dentro de
  `st.fragment(run_every=300)`. Só esse fragmento roda de novo; o canvas lê o
  bloco (documento pai, mesma origem) e funde os nós: quem continua fica onde
  está, os novos crescem do nada, os que saíram encolhem até sumir.
- O JSON vai em blocos de 5 KB: mensagens acima de 10 KB o Streamlit manda só
  como referência de cache, e o elemento pode chegar vazio.
- Desempenho no celular: sombras pré-renderizadas em sprites (nada de
  `shadowBlur` por quadro), fios finos com no máximo 1 pixel físico (o
  rasterizador usa o caminho rápido), um stroke por fio forte e
  `devicePixelRatio` limitado a 2.
- Diagnóstico no console do iframe: `__descanso()` devolve nº de nós, fios e o
  custo de JS por quadro.

Variáveis só para teste: `DESCANSO_DB_LOCAL` (arquivo SQLite com o mesmo
esquema, no lugar do Turso) e `DESCANSO_RECARREGAR_S` (intervalo de recarga).
