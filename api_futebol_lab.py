
import requests
import streamlit as st

# ============================================================
# LABORATÓRIO API FUTEBOL — SÉRIE B
# ============================================================
# Independente do Main.py.
# Não altera o cache do Premium e não consulta API-Sports.
#
# Configure no Streamlit Secrets:
#
# [api_futebol]
# token = "SUA_CHAVE"
#
# Base documentada:
# https://api.api-futebol.com.br/v1
# Autenticação:
# Authorization: Bearer TOKEN
# ============================================================

BASE_URL = "https://api.api-futebol.com.br/v1"

st.set_page_config(
    page_title="Laboratório API Futebol",
    page_icon="🧪",
    layout="wide",
)

st.title("🧪 Laboratório API Futebol")
st.caption("Série B — teste independente antes da integração ao Premium")

def get_token():
    try:
        if "api_futebol" in st.secrets:
            return st.secrets["api_futebol"].get("token")
    except Exception:
        pass

    try:
        return st.secrets.get("API_FUTEBOL_TOKEN")
    except Exception:
        return None

TOKEN = get_token()

def api_get(path, params=None):
    if not TOKEN:
        return None, "API_FUTEBOL_TOKEN não configurado nos Secrets."

    try:
        r = requests.get(
            BASE_URL + path,
            params=params or {},
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Accept": "application/json",
            },
            timeout=20,
        )

        if r.status_code == 401:
            return None, "HTTP 401 — token inválido ou não autorizado."
        if r.status_code == 403:
            return None, "HTTP 403 — acesso negado/plano não liberou este recurso."
        if r.status_code == 429:
            return None, "HTTP 429 — limite de requisições atingido."
        if not r.ok:
            return None, f"HTTP {r.status_code}: {r.text[:800]}"

        try:
            return r.json(), None
        except Exception:
            return None, "Resposta não-JSON."

    except Exception as e:
        return None, str(e)

def first_list(data, keys):
    if not isinstance(data, dict):
        return []
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            return value
    return []

def show_raw(label, data):
    with st.expander(label):
        st.json(data if data is not None else {})

# ------------------------------------------------------------
# 0 — STATUS DO TOKEN
# ------------------------------------------------------------
st.header("0. Conexão")

if not TOKEN:
    st.error(
        "Configure a chave nos Secrets do Streamlit antes de testar. "
        "A chave não precisa ser colocada neste arquivo."
    )
else:
    st.success("🔐 Token encontrado nos Secrets.")

# ------------------------------------------------------------
# 1 — CAMPEONATOS
# ------------------------------------------------------------
st.header("1. Campeonatos liberados")

if st.button("🏆 Listar campeonatos", type="primary"):
    data, error = api_get("/campeonatos")

    if error:
        st.error(error)
    else:
        st.session_state["campeonatos"] = data
        comps = first_list(data, ["campeonatos", "data", "results"])

        st.success(f"Resposta recebida. {len(comps)} campeonato(s) listado(s).")

        if comps:
            rows = []
            for c in comps:
                rows.append({
                    "ID": c.get("id"),
                    "Nome": c.get("nome") or c.get("name"),
                    "Temporada": c.get("temporada") or c.get("season"),
                    "País": c.get("pais") or c.get("country"),
                })
            st.dataframe(rows, use_container_width=True, hide_index=True)

        show_raw("🔍 JSON — campeonatos", data)

# ------------------------------------------------------------
# 2 — ID DA SÉRIE B
# ------------------------------------------------------------
st.header("2. Identificar Série B")

campeonatos = st.session_state.get("campeonatos")
comps = first_list(campeonatos, ["campeonatos", "data", "results"])

serie_b_ids = []
if comps:
    for c in comps:
        text = " ".join(
            str(c.get(k) or "")
            for k in ["nome", "name", "slug", "descricao", "description"]
        ).lower()
        if "série b" in text or "serie b" in text:
            serie_b_ids.append(
                (str(c.get("id")), c.get("nome") or c.get("name"))
            )

if serie_b_ids:
    st.success("Série B encontrada na lista.")
    st.write(serie_b_ids)

manual_championship_id = st.text_input(
    "ID do campeonato Série B (se necessário)",
    value=serie_b_ids[0][0] if serie_b_ids else "",
)

# ------------------------------------------------------------
# 3 — FASES
# ------------------------------------------------------------
st.header("3. Fases da Série B")

if st.button("📚 Carregar fases"):
    cid = manual_championship_id.strip()

    if not cid:
        st.warning("Informe o ID da Série B.")
    else:
        data, error = api_get(f"/campeonatos/{cid}/fases")

        if error:
            st.error(error)
        else:
            st.session_state["fases"] = data
            phases = first_list(data, ["fases", "data", "results"])

            st.success(f"Resposta recebida. {len(phases)} fase(s).")

            if phases:
                rows = []
                for p in phases:
                    rows.append({
                        "ID": p.get("id"),
                        "Nome": p.get("nome") or p.get("name"),
                        "Status": p.get("status"),
                    })
                st.dataframe(rows, use_container_width=True, hide_index=True)

            show_raw("🔍 JSON — fases", data)

# ------------------------------------------------------------
# 4 — DETALHE DE UMA FASE
# ------------------------------------------------------------
st.header("4. Detalhe da fase")

fases_data = st.session_state.get("fases")
phases = first_list(fases_data, ["fases", "data", "results"])

phase_id = st.text_input(
    "ID da fase",
    value=str(phases[0].get("id")) if phases and phases[0].get("id") else "",
)

if st.button("📋 Consultar fase"):
    cid = manual_championship_id.strip()

    if not cid or not phase_id.strip():
        st.warning("Informe campeonato_id e fase_id.")
    else:
        data, error = api_get(
            f"/campeonatos/{cid}/fases/{phase_id.strip()}"
        )

        if error:
            st.error(error)
        else:
            st.session_state["fase_detail"] = data
            st.success("✅ Fase carregada.")
            show_raw("🔍 JSON — detalhe da fase", data)

# ------------------------------------------------------------
# 5 — PARTIDA
# ------------------------------------------------------------
st.header("5. Enriquecimento de uma partida")

st.write(
    "Cole o ID de uma partida FINALIZADA da Série B. "
    "O endpoint de partida é o recurso mais rico da API."
)

fixture_id = st.text_input(
    "ID da partida",
    value="",
    placeholder="Ex.: 23447",
)

if st.button("🔬 Testar partida"):
    fid = fixture_id.strip()

    if not fid:
        st.warning("Informe o ID da partida.")
        st.stop()

    data, error = api_get(f"/partidas/{fid}")

    if error:
        st.error(error)
    else:
        st.session_state["partida"] = data

        # Tentativa de localizar o objeto principal.
        partida = data.get("partida", data)

        st.success("✅ Detalhes da partida recebidos.")

        # -------------------------
        # Resumo
        # -------------------------
        st.subheader("⚽ Resumo")

        home = (
            partida.get("time_mandante")
            or partida.get("mandante")
            or partida.get("home_team")
            or partida.get("home")
        )
        away = (
            partida.get("time_visitante")
            or partida.get("visitante")
            or partida.get("away_team")
            or partida.get("away")
        )

        c1, c2, c3 = st.columns(3)
        with c1:
            st.write("**Casa**")
            st.write(home if isinstance(home, str) else str(home or "—"))
        with c2:
            st.write("**Fora**")
            st.write(away if isinstance(away, str) else str(away or "—"))
        with c3:
            st.write("**ID**")
            st.write(fid)

        # -------------------------
        # Descoberta automática
        # -------------------------
        st.subheader("🧩 Estrutura encontrada")

        if isinstance(partida, dict):
            keys = sorted(partida.keys())
            st.write(
                f"**{len(keys)} campos no objeto principal da partida:**"
            )
            st.code("\n".join(keys))

        # -------------------------
        # Cobertura
        # -------------------------
        st.subheader("📊 Mapa de cobertura")

        aliases = {
            "Placar": ["placar", "resultado", "score"],
            "Estatísticas": ["estatisticas", "statistics", "stats"],
            "Escalações": ["escalacoes", "escalações", "lineups"],
            "Titulares": ["titulares", "starters"],
            "Reservas": ["reservas", "substitutes"],
            "Eventos": ["eventos", "events", "gols", "cartoes", "substituicoes"],
            "Gols": ["gols", "goals"],
            "Cartões": ["cartoes", "cartões", "cards"],
            "Substituições": ["substituicoes", "substituições", "substitutions"],
            "Jogadores": ["jogadores", "players", "atletas"],
            "Finalizações": ["finalizacoes", "finalizações", "shots"],
            "Passes": ["passes"],
            "Desarmes": ["desarmes", "tackles"],
            "Posse": ["posse", "possession"],
            "Escanteios": ["escanteios", "corners"],
            "Impedimentos": ["impedimentos", "offsides"],
            "Faltas": ["faltas", "fouls"],
            "Goleiros": ["goleiros", "goalkeepers", "defesas", "saves"],
            "xG": ["xg", "expected_goals", "gols_esperados"],
        }

        rows = []
        lower_keys = {
            str(k).lower(): k
            for k in (partida.keys() if isinstance(partida, dict) else [])
        }

        for label, possible in aliases.items():
            found = []
            for p in possible:
                if p.lower() in lower_keys:
                    found.append(lower_keys[p.lower()])

            rows.append({
                "Dado": label,
                "Encontrado": "✅" if found else "❌",
                "Campo(s)": ", ".join(map(str, found)) if found else "—",
            })

        st.dataframe(rows, use_container_width=True, hide_index=True)

        # -------------------------
        # JSON completo
        # -------------------------
        show_raw("🔍 JSON bruto — partida", data)

# ------------------------------------------------------------
# 6 — CHECKLIST FINAL
# ------------------------------------------------------------
st.divider()
st.header("6. Checklist para integração")

st.write(
    """
Depois do teste, vamos decidir objetivamente:

1. Qual é o ID da Série B 2026.
2. Qual é o ID da fase.
3. Como listar as partidas.
4. Qual é o ID único de cada partida.
5. Quais campos de estatística existem.
6. Se escalações e jogadores estão completos.
7. Se eventos estão completos.
8. Quais métricas podem alimentar o histórico dos times.
9. Quais métricas podem alimentar o histórico dos jogadores.
10. Quais campos podem ser usados para validação cruzada com outras fontes.
"""
)

st.info(
    "Não coloque sua API Key neste arquivo nem no chat. "
    "Use o Secrets do Streamlit."
)
