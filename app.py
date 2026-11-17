"""Descanso de tela da CAMDA — rede de nós e fios, sem nenhum texto na tela.

Faltas, sobras (tabela `divergencias`) e tarefas pendentes do Risca (tabela
`tarefas`) do mesmo banco Turso do CAMDA Estoque viram bolinhas flutuando.
A informação só aparece num tooltip ao passar o mouse (ou tocar) num nó.

Como a animação não "pula" ao recarregar
-----------------------------------------
O canvas (`st.components.v1.html`) é desenhado UMA vez, com um HTML que nunca
muda — então o iframe nunca é recriado. Os dados vão para a página num bloco
escondido dentro de um `st.fragment(run_every=300)`: a cada 5 minutos só esse
fragmento roda de novo, e o JS do canvas (que lê o documento pai, mesma origem)
percebe a versão nova e funde os nós: os que continuam ficam onde estão, os
novos crescem do nada e os que saíram encolhem até sumir.
"""

from __future__ import annotations

import hashlib
import html
import json
import logging
import os
import re
import time
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

log = logging.getLogger("descanso")

RECARREGAR_S = int(os.environ.get("DESCANSO_RECARREGAR_S", "300"))  # 5 minutos
CHUNK = 5000                # bytes por bloco de dados (o Streamlit cacheia mensagens > 10 KB)
AQUI = Path(__file__).parent
CANVAS_HTML = (AQUI / "descanso.html").read_text(encoding="utf-8")

st.set_page_config(
    page_title="Descanso de tela",
    page_icon="⚫",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── CSS: some com todo o chrome do Streamlit e põe o canvas na tela inteira ──
st.html(
    """
<style>
header[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"],
[data-testid="collapsedControl"], [data-testid="stStatusWidget"],
[data-testid="stAppDeployButton"], [data-testid="stMainMenu"], #MainMenu, footer,
.st-key-dsc_dados { display: none !important; }
html, body, .stApp, [data-testid="stApp"], [data-testid="stAppViewContainer"],
[data-testid="stMain"] {
  background: #f4f4f2 !important; overflow: hidden !important;
}
.block-container, [data-testid="stMainBlockContainer"], [data-testid="stMain"] {
  padding: 0 !important; margin: 0 !important; max-width: 100% !important;
}
.st-key-dsc_canvas {
  position: fixed !important; inset: 0 !important; z-index: 10;
  width: 100vw !important; height: 100vh !important; height: 100dvh !important;
}
.st-key-dsc_canvas > div, .st-key-dsc_canvas .stElementContainer,
.st-key-dsc_canvas [data-testid="stElementContainer"], .st-key-dsc_canvas iframe {
  width: 100% !important; height: 100% !important; border: 0 !important;
  display: block !important; flex: 1 1 100% !important; min-height: 0 !important;
}
</style>
"""
)


# ── Leitura do Turso ────────────────────────────────────────────────────────
def _segredo(nome: str) -> str:
    try:
        v = st.secrets.get(nome)
        if v:
            return str(v)
    except Exception:
        pass
    return os.environ.get(nome, "")


def _conectar():
    """Conexão remota com o Turso (HTTP). Sem réplica local: a leitura é
    pequena (~100 divergências + tarefas pendentes) e roda 1x a cada 5 min,
    compartilhada por todas as telas abertas (cache_data)."""
    import libsql

    local = os.environ.get("DESCANSO_DB_LOCAL", "")
    if local:  # testes: arquivo SQLite com o mesmo esquema
        return libsql.connect(local)
    url = _segredo("TURSO_DATABASE_URL")
    token = _segredo("TURSO_AUTH_TOKEN")
    if not (url and token):
        return None
    return libsql.connect(url, auth_token=token)


_RE_VOL = re.compile(r"(\d+(?:[.,]\d+)?)\s*(L|LT|LTS|ML)\b")


def qtd_fisica(produto: str, qtd: int) -> str:
    """Quantidade na embalagem física: baldes (20 L), galões (10 L),
    frascos + caixas 5L x 4 (5 L), frascos (< 5 L) ou un."""
    q = abs(int(qtd or 0))
    nome = str(produto or "").upper()
    m = _RE_VOL.search(nome)
    if not m:
        return f"{q} un."
    litros = float(m.group(1).replace(",", "."))
    if m.group(2) == "ML":
        litros /= 1000.0
    if litros >= 15:
        return f"{q} balde" if q == 1 else f"{q} baldes"
    if litros >= 10:
        return f"{q} galão" if q == 1 else f"{q} galões"
    if litros >= 5:
        base = f"{q} frasco" if q == 1 else f"{q} frascos"
        cx, resto = divmod(q, 4)
        if cx == 0:
            return base
        return f"{base} = {cx} cx" + (f" + {resto}" if resto else "")
    return f"{q} frasco" if q == 1 else f"{q} frascos"


_PRIO = {1: "urgente", 2: "normal", 3: "quando_der"}


def _ler_banco() -> dict | None:
    conn = _conectar()
    if conn is None:
        return None
    try:
        rows = conn.execute(
            "SELECT id, codigo, produto, delta, COALESCE(cooperado, '') "
            "FROM divergencias WHERE delta != 0"
        ).fetchall()
        div = []
        for i, cod, prod, delta, coop in rows:
            delta = int(delta or 0)
            div.append([
                int(i), str(cod or "").strip(), str(prod or "").strip(), delta,
                str(coop or "").strip(), qtd_fisica(prod, delta),
            ])
        try:
            trows = conn.execute(
                "SELECT id, prioridade, texto, COALESCE(prazo, '') "
                "FROM tarefas WHERE feita = 0"
            ).fetchall()
        except Exception as e:  # tabela ainda não criada pelo Risca
            log.warning("tarefas indisponível: %s", e)
            trows = []
        tar = [
            [str(i), _PRIO.get(int(p or 2), "normal"), str(t or "").strip(), str(pz or "")]
            for i, p, t, pz in trows
        ]
        return {"d": div, "t": tar}
    finally:
        try:
            conn.close()
        except Exception:
            pass


@st.cache_resource
def _ultimo_bom() -> dict:
    return {}


@st.cache_data(ttl=max(5, RECARREGAR_S - 30), show_spinner=False)
def carregar() -> tuple[dict, float]:
    """(dados para o canvas, hora da leitura boa). Se o banco falhar, devolve a
    última leitura boa (a tela não pode esvaziar por causa de um soluço de
    rede), mas com a hora antiga: o canvas expõe essa idade em __descanso() e
    o log avisa a cada recarga em que a leitura falhou."""
    memo = _ultimo_bom()
    try:
        dados = _ler_banco()
        if dados is None:
            log.error("sem credenciais do Turso (TURSO_DATABASE_URL / TURSO_AUTH_TOKEN)")
            return memo.get("dados") or {"d": [], "t": []}, memo.get("lido_em", 0.0)
        memo["dados"], memo["lido_em"] = dados, time.time()
        return dados, memo["lido_em"]
    except Exception as e:
        idade = (time.time() - memo.get("lido_em", time.time())) / 60
        log.error("falha ao ler o Turso (mostrando dados de %.0f min atrás): %s", idade, e)
        if memo.get("dados"):
            return memo["dados"], memo["lido_em"]
        raise  # sem cache bom: não guarda o vazio no cache_data


# ── Canvas: HTML constante → o iframe nunca é recriado ──────────────────────
with st.container(key="dsc_canvas"):
    components.html(CANVAS_HTML, height=600, scrolling=False)


@st.fragment(run_every=RECARREGAR_S)
def _dados():
    try:
        dados, lido_em = carregar()
    except Exception:
        dados, lido_em = {"d": [], "t": []}, 0.0
    s = json.dumps(dados, ensure_ascii=False, separators=(",", ":"))
    v = hashlib.sha1(s.encode("utf-8")).hexdigest()[:12]
    partes = [s[i:i + CHUNK] for i in range(0, len(s), CHUNK)] or [""]
    # data-t muda a cada execução do fragmento (pulso): se parar de mudar, a
    # conexão com o servidor morreu e o canvas recarrega a página sozinho.
    pulso = f'data-t="{time.time():.0f}" data-r="{RECARREGAR_S}" data-lido="{lido_em:.0f}"'
    with st.container(key="dsc_dados"):
        for i, p in enumerate(partes):
            st.html(
                f'<div class="dsc-chunk" data-v="{v}" data-i="{i}" data-n="{len(partes)}" '
                f'{pulso} hidden>{html.escape(p, quote=False)}</div>'
            )


_dados()
