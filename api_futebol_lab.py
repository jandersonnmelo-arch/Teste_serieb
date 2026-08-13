
import requests
import streamlit as st
import json

# ============================================================
# LABORATÓRIO API FUTEBOL — DIAGNÓSTICO DE RESPOSTA
# ============================================================
# Versão diagnóstica: não altera o Main.py nem o cache.
# Objetivo: descobrir a estrutura REAL retornada pela API.
#
# Secrets aceitos:
# [api_futebol]
# token = "SUA_CHAVE"
#
# ou:
# API_FUTEBOL_TOKEN = "SUA_CHAVE"
# ============================================================

BASE_URL = "https://api.api-futebol.com.br/v1"

st.set_page_config(
    page_title="Diagnóstico API Futebol",
    page_icon="🧪",
    layout="wide",
)

st.title("🧪 Diagnóstico API Futebol")
st.caption("Descobrindo a resposta real da sua conta Free — Série B")

def get_token():
    try:
        if "api_futebol" in st.secrets:
            token = st.secrets["api_futebol"].get("token")
            if token:
                return token
    except Exception:
        pass

    try:
        token = st.secrets.get("API_FUTEBOL_TOKEN")
        if token:
            return token
    except Exception:
        pass

    return None

TOKEN = get_token()

def api_get(path, params=None):
    if not TOKEN:
        return None, None, None, "Token não encontrado nos Secrets."

    try:
        r = requests.get(
            BASE_URL + path,
            params=params or {},
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Accept": "application/json",
            },
            timeout=25,
        )

        try:
            body = r.json()
        except Exception:
            body = r.text

        headers = {
            k: v for k, v in r.headers.items()
            if k.lower() in {
                "content-type",
                "x-ratelimit-limit",
                "x-ratelimit-remaining",
                "x-ratelimit-reset",
                "retry-after",
            }
        }

        if not r.ok:
            return body, r.status_code, headers, (
                f"HTTP {r.status_code}"
            )

        return body, r.status_code, headers, None

    except Exception as e:
        return None, None, None, str(e)

def walk(obj, path=""):
    """Percorre recursivamente dict/list procurando textos relacionados."""
    found = []

    if isinstance(obj, dict):
        for key, value in obj.items():
            current = f"{path}.{key}" if path else str(key)

            key_text = str(key).lower()
            if any(term in key_text for term in [
                "campeonato", "league", "nome", "name", "serie"
            ]):
                found.append((current, value))

            found.extend(walk(value, current))

    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            found.extend(walk(value, f"{path}[{i}]"))

    elif isinstance(obj, str):
        text = obj.lower()
        if "série b" in text or "serie b" in text:
            found.append((path, obj))

    return found

def extract_ids(obj, path=""):
    """Procura objetos com campos que parecem IDs + nomes."""
    results = []

    if isinstance(obj, dict):
        keys_lower = {str(k).lower(): k for k in obj.keys()}

        id_key = next(
            (keys_lower[k] for k in ["id", "campeonato_id", "league_id"]
             if k in keys_lower),
            None,
        )
        name_key = next(
            (keys_lower[k] for k in [
                "nome", "name", "campeonato", "league", "descricao"
            ] if k in keys_lower),
            None,
        )

        if id_key is not None or name_key is not None:
            value_name = obj.get(name_key) if name_key else None
            value_id = obj.get(id_key) if id_key else None

            if value_name is not None or value_id is not None:
                results.append({
                    "caminho": path,
                    "ID": value_id,
                    "Nome": value_name,
                    "objeto": obj,
                })

        for key, value in obj.items():
            current = f"{path}.{key}" if path else str(key)
            results.extend(extract_ids(value, current))

    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            results.extend(extract_ids(value, f"{path}[{i}]"))

    return results

# ------------------------------------------------------------
# CONEXÃO
# ------------------------------------------------------------
st.header("0. Conexão")

if TOKEN:
    st.success("🔐 Token encontrado nos Secrets.")
else:
    st.error("Token não encontrado. Configure o Secret antes de testar.")

# ------------------------------------------------------------
# TESTE PRINCIPAL
# ------------------------------------------------------------
st.header("1. Resposta REAL de /campeonatos")

st.write(
    "Este teste não tenta adivinhar a estrutura da resposta. "
    "Ele mostra status, headers relevantes e o JSON bruto."
)

if st.button("🔎 Consultar /campeonatos", type="primary"):
    body, status, headers, error = api_get("/campeonatos")

    st.session_state["champ_body"] = body
    st.session_state["champ_status"] = status
    st.session_state["champ_headers"] = headers
    st.session_state["champ_error"] = error

if "champ_status" in st.session_state:
    status = st.session_state["champ_status"]
    body = st.session_state["champ_body"]
    headers = st.session_state["champ_headers"]
    error = st.session_state["champ_error"]

    c1, c2 = st.columns(2)
    with c1:
        st.metric("HTTP", status if status is not None else "—")
    with c2:
        remaining = headers.get("x-ratelimit-remaining", "—") if headers else "—"
        st.metric("Rate limit restante", remaining)

    if error:
        st.error(error)

    if headers:
        st.subheader("📡 Headers relevantes")
        st.json(headers)

    st.subheader("🧬 Tipo da resposta")
    st.code(type(body).__name__)

    st.subheader("🔍 JSON bruto")
    st.json(body)

    # --------------------------------------------
    # Busca recursiva por Série B
    # --------------------------------------------
    st.subheader("🇧🇷 Busca automática por Série B")

    matches = walk(body)

    serie_matches = [
        item for item in matches
        if "série b" in str(item[1]).lower()
        or "serie b" in str(item[1]).lower()
    ]

    if serie_matches:
        st.success(
            f"Encontrada(s) {len(serie_matches)} ocorrência(s) "
            "relacionada(s) à Série B."
        )

        for path, value in serie_matches:
            st.write(f"**{path}**")
            st.write(value)
    else:
        st.warning(
            "Nenhuma ocorrência literal de 'Série B' foi encontrada "
            "no JSON retornado."
        )

    # --------------------------------------------
    # Objetos com ID/Nome
    # --------------------------------------------
    st.subheader("🆔 Objetos com ID/Nome encontrados")

    candidates = extract_ids(body)

    if candidates:
        rows = []
        seen = set()

        for item in candidates:
            key = (
                str(item.get("ID")),
                str(item.get("Nome")),
                str(item.get("caminho")),
            )
            if key in seen:
                continue
            seen.add(key)

            rows.append({
                "ID": item.get("ID"),
                "Nome": item.get("Nome"),
                "Caminho": item.get("caminho"),
            })

        st.dataframe(
            rows,
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Nenhum objeto ID/Nome reconhecível foi encontrado.")

# ------------------------------------------------------------
# TESTE DIRETO POR ID
# ------------------------------------------------------------
st.divider()
st.header("2. Teste direto de campeonato")

st.write(
    "Depois de identificar o ID da Série B no diagnóstico, "
    "coloque-o abaixo. Não faremos novas tentativas automáticas."
)

champ_id = st.text_input(
    "ID do campeonato",
    placeholder="Ex.: 10",
)

if st.button("🏆 Consultar campeonato por ID"):
    if not champ_id.strip():
        st.warning("Informe um ID.")
    else:
        body, status, headers, error = api_get(
            f"/campeonatos/{champ_id.strip()}"
        )

        st.write(f"**HTTP:** {status}")
        if headers:
            st.json(headers)

        if error:
            st.error(error)
        else:
            st.success("Resposta recebida.")
            st.json(body)

# ------------------------------------------------------------
# TESTE DE FASE POR ID
# ------------------------------------------------------------
st.header("3. Teste direto de fase")

phase_id = st.text_input(
    "ID da fase",
    placeholder="ID retornado pelo campeonato",
)

if st.button("📚 Consultar fase"):
    if not champ_id.strip() or not phase_id.strip():
        st.warning("Informe campeonato ID e fase ID.")
    else:
        body, status, headers, error = api_get(
            f"/campeonatos/{champ_id.strip()}/fases/{phase_id.strip()}"
        )

        st.write(f"**HTTP:** {status}")

        if error:
            st.error(error)
        else:
            st.success("Fase recebida.")
            st.json(body)

# ------------------------------------------------------------
# TESTE DE PARTIDA
# ------------------------------------------------------------
st.header("4. Teste de partida")

fixture_id = st.text_input(
    "ID da partida",
    placeholder="ID de uma partida finalizada da Série B",
)

if st.button("🔬 Consultar partida"):
    if not fixture_id.strip():
        st.warning("Informe o ID da partida.")
    else:
        body, status, headers, error = api_get(
            f"/partidas/{fixture_id.strip()}"
        )

        st.write(f"**HTTP:** {status}")

        if headers:
            st.json(headers)

        if error:
            st.error(error)
        else:
            st.success("Partida recebida.")
            st.json(body)

            # Campos de interesse encontrados em qualquer nível.
            found = walk(body)

            interesting = [
                item for item in found
                if any(term in item[0].lower() for term in [
                    "estat", "escal", "jog", "atlet", "gol",
                    "cart", "substit", "final", "passe",
                    "escante", "posse", "falta", "imped",
                    "goleir", "xg"
                ])
            ]

            if interesting:
                st.subheader("📊 Campos potencialmente úteis")
                for path, value in interesting[:200]:
                    st.write(f"**{path}**")
                    st.write(value)

st.divider()
st.info(
    "Esta versão é somente diagnóstico. Depois de descobrirmos a estrutura "
    "real da API, fazemos o laboratório de cobertura e só então a integração "
    "ao Premium."
)
