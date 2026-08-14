"""
motor_historico_analistas.py

Camada incremental para o Premium Football Analytics.

Objetivo:
- Ler SOMENTE partidas já enriquecidas e persistidas no cache.
- Construir/atualizar o histórico dos times e jogadores.
- Entregar ao analista uma base estatística pronta.
- Nunca chamar a API.
- Não apagar nem substituir os registros brutos de partidas enriquecidas.

Compatível com o cache da API Futebol — Série B validado no laboratório.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional, Tuple


def _first(obj: Any, keys: Iterable[str], default=None):
    if not isinstance(obj, dict):
        return default
    for key in keys:
        value = obj.get(key)
        if value is not None and value != "":
            return value
    return default


def _num(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        value = value.strip().replace("%", "").replace(",", ".")
        try:
            return float(value)
        except Exception:
            return None
    return None


def _norm_name(value):
    return " ".join(str(value or "").strip().lower().split())


def _team_key(team):
    if not isinstance(team, dict):
        return None

    team_id = _first(team, ("id", "time_id", "team_id"))
    if team_id is not None:
        return str(team_id)

    name = _first(team, ("nome", "nome_popular", "name"))
    return _norm_name(name) or None


def _team_name(team):
    return _first(
        team,
        ("nome", "nome_popular", "name"),
        "Desconhecido",
    )


def _score(enriched):
    score = enriched.get("placar") or {}

    if not isinstance(score, dict):
        return None, None

    home = _num(
        _first(
            score,
            (
                "casa",
                "mandante",
                "home",
                "home_score",
                "gols_mandante",
            ),
        )
    )

    away = _num(
        _first(
            score,
            (
                "fora",
                "visitante",
                "away",
                "away_score",
                "gols_visitante",
            ),
        )
    )

    return home, away


STAT_ALIASES = {
    "escanteios": (
        "corner",
        "corners",
        "escanteio",
        "escanteios",
    ),
    "finalizacoes": (
        "shots",
        "shot",
        "finalizacao",
        "finalizacoes",
        "total shots",
    ),
    "finalizacoes_no_alvo": (
        "shots on goal",
        "shots on target",
        "finalizacoes no alvo",
        "finalizacao no alvo",
    ),
    "posse": (
        "possession",
        "posse",
    ),
    "faltas": (
        "fouls",
        "foul",
        "faltas",
    ),
    "cartoes_amarelos": (
        "yellow",
        "yellow cards",
        "cartao amarelo",
        "cartoes amarelos",
    ),
    "cartoes_vermelhos": (
        "red",
        "red cards",
        "cartao vermelho",
        "cartoes vermelhos",
    ),
    "impedimentos": (
        "offsides",
        "offside",
        "impedimentos",
    ),
    "penaltis": (
        "penalty",
        "penalties",
        "penaltis",
        "pênaltis",
    ),
}


def _stat_name(stat):
    if not isinstance(stat, dict):
        return ""

    return _norm_name(
        _first(
            stat,
            (
                "tipo",
                "nome",
                "name",
                "estatistica",
                "statistic",
                "key",
            ),
            "",
        )
    )


def _stat_value(stat):
    if not isinstance(stat, dict):
        return None

    return _num(
        _first(
            stat,
            ("valor", "value", "val", "amount"),
        )
    )


def _match_stat_value(stats, aliases):
    aliases_norm = tuple(_norm_name(x) for x in aliases)

    for stat in stats or []:
        name = _stat_name(stat)

        if any(
            alias in name or name in alias
            for alias in aliases_norm
        ):
            return _stat_value(stat)

    return None


def _side_stats(stats, side):
    """
    Aceita formatos comuns:

    1) [{"tipo": "...", "casa": 5, "fora": 3}]
    2) [{"tipo": "...", "valor": {"casa": 5, "fora": 3}}]
    3) {"casa": [...], "fora": [...]}
    """

    if isinstance(stats, dict):
        direct = stats.get(side)

        if isinstance(direct, list):
            return {
                metric: _match_stat_value(
                    direct,
                    aliases,
                )
                for metric, aliases in STAT_ALIASES.items()
            }

    result = {}

    for metric, aliases in STAT_ALIASES.items():
        value = None
        aliases_norm = tuple(_norm_name(x) for x in aliases)

        for stat in stats or []:
            if not isinstance(stat, dict):
                continue

            name = _stat_name(stat)

            if not any(
                alias in name or name in alias
                for alias in aliases_norm
            ):
                continue

            raw = _first(
                stat,
                ("valor", "value", "val", "amount"),
            )

            if isinstance(raw, dict):
                value = _num(
                    _first(
                        raw,
                        (
                            side,
                            "home" if side == "casa" else "away",
                        ),
                    )
                )
            else:
                value = _num(
                    _first(
                        stat,
                        (
                            side,
                            "mandante"
                            if side == "casa"
                            else "visitante",
                            "home" if side == "casa" else "away",
                        ),
                    )
                )

            if value is not None:
                break

        result[metric] = value

    return result


def iter_enriched_matches(cache):
    """
    Itera exclusivamente sobre partidas já enriquecidas.
    Nenhuma chamada externa é realizada.
    """

    seen = set()

    bucket = cache.get("partidas_enriquecidas") or {}

    if not isinstance(bucket, dict):
        return

    for key, match in bucket.items():
        if not isinstance(match, dict):
            continue

        match_id = str(
            match.get("partida_id", key)
        )

        if match_id in seen:
            continue

        seen.add(match_id)
        yield match


def rebuild_historical_indexes(cache):
    """
    Reconstrói os índices derivados:

        cache["historico_times"]
        cache["historico_jogadores"]

    A operação é local e usa somente:
        cache["partidas_enriquecidas"]

    Os registros enriquecidos originais NÃO são removidos.
    """

    team_history = {}
    player_history = {}

    enriched_count = 0

    for match in iter_enriched_matches(cache):
        enriched_count += 1

        teams = match.get("times") or {}

        home = teams.get("casa") or {}
        away = teams.get("fora") or {}

        home_score, away_score = _score(match)

        stats = match.get("estatisticas") or []
        date_value = match.get("data")
        status = match.get("status")

        sides = (
            (
                "casa",
                home,
                home_score,
                away_score,
                away,
            ),
            (
                "fora",
                away,
                away_score,
                home_score,
                home,
            ),
        )

        for side, team, own_goals, opp_goals, opponent in sides:
            team_key = _team_key(team)

            if not team_key:
                continue

            bucket = team_history.setdefault(
                team_key,
                {
                    "time_id": _first(
                        team,
                        (
                            "id",
                            "time_id",
                            "team_id",
                        ),
                    ),
                    "nome": _team_name(team),
                    "jogos": [],
                },
            )

            match_id = str(
                match.get("partida_id")
            )

            record = {
                "partida_id": match_id,
                "mandante": side == "casa",
                "adversario": opponent,
                "gols_feitos": own_goals,
                "gols_sofridos": opp_goals,
                "placar": match.get("placar") or {},
                "estatisticas": _side_stats(
                    stats,
                    side,
                ),
                "eventos": match.get("eventos") or [],
                "data": date_value,
                "status": status,
            }

            if not any(
                str(item.get("partida_id")) == match_id
                for item in bucket["jogos"]
            ):
                bucket["jogos"].append(record)

        # ---------------------------------------------
        # HISTÓRICO INDIVIDUAL DOS JOGADORES
        # ---------------------------------------------

        players = match.get("jogadores") or []

        if isinstance(players, list):
            for player in players:
                if not isinstance(player, dict):
                    continue

                player_id = _first(
                    player,
                    (
                        "id",
                        "jogador_id",
                        "player_id",
                    ),
                )

                if player_id is None:
                    continue

                player_key = str(player_id)

                player_bucket = player_history.setdefault(
                    player_key,
                    {
                        "jogador_id": player_id,
                        "nome": _first(
                            player,
                            ("nome", "name"),
                            f"Jogador {player_id}",
                        ),
                        "time": _first(
                            player,
                            ("time", "team"),
                            {},
                        ),
                        "jogos": [],
                    },
                )

                player_stats = (
                    player.get("estatisticas")
                    or player.get("stats")
                    or {}
                )

                player_bucket["jogos"].append(
                    {
                        "partida_id": str(
                            match.get("partida_id")
                        ),
                        "data": date_value,
                        "status": status,
                        "estatisticas": player_stats,
                        "titular": _first(
                            player,
                            (
                                "titular",
                                "starter",
                                "starting",
                            ),
                        ),
                        "minutos": _num(
                            _first(
                                player,
                                (
                                    "minutos",
                                    "minutes",
                                ),
                            )
                        ),
                    }
                )

    for bucket in team_history.values():
        bucket["jogos"].sort(
            key=lambda item: str(
                item.get("data") or ""
            )
        )

    for bucket in player_history.values():
        bucket["jogos"].sort(
            key=lambda item: str(
                item.get("data") or ""
            )
        )

    cache["historico_times"] = team_history
    cache["historico_jogadores"] = player_history

    return {
        "partidas_enriquecidas": enriched_count,
        "times": len(team_history),
        "jogadores": len(player_history),
    }


def _find_team_bucket(cache, team_ref):
    history = cache.get("historico_times") or {}

    if str(team_ref) in history:
        return history[str(team_ref)]

    target = _norm_name(team_ref)

    for bucket in history.values():
        if _norm_name(bucket.get("nome")) == target:
            return bucket

    return None


def summarize_team_history(
    cache,
    team_ref,
    limit=10,
    venue: Optional[str] = None,
):
    """
    Gera o resumo estatístico usado pelos analistas.

    venue:
        None  -> todos
        "casa" -> somente mandante
        "fora" -> somente visitante
    """

    bucket = _find_team_bucket(
        cache,
        team_ref,
    )

    if not bucket:
        return {
            "disponivel": False,
            "time": str(team_ref),
            "jogos_analisados": 0,
        }

    games = list(
        bucket.get("jogos") or []
    )

    if venue == "casa":
        games = [
            game
            for game in games
            if game.get("mandante") is True
        ]

    elif venue == "fora":
        games = [
            game
            for game in games
            if game.get("mandante") is False
        ]

    games = games[
        -max(1, int(limit)):
    ]

    finished = [
        game
        for game in games
        if (
            _num(game.get("gols_feitos"))
            is not None
            and
            _num(game.get("gols_sofridos"))
            is not None
        )
    ]

    wins = 0
    draws = 0
    losses = 0

    for game in finished:
        gf = float(
            game["gols_feitos"]
        )
        ga = float(
            game["gols_sofridos"]
        )

        if gf > ga:
            wins += 1
        elif gf == ga:
            draws += 1
        else:
            losses += 1

    def average(metric):
        values = [
            _num(
                game.get(
                    "estatisticas",
                    {},
                ).get(metric)
            )
            for game in games
        ]

        values = [
            value
            for value in values
            if value is not None
        ]

        if not values:
            return None

        return round(
            sum(values) / len(values),
            2,
        )

    games_with_score = len(finished)

    goals_for = sum(
        float(game["gols_feitos"])
        for game in finished
    )

    goals_against = sum(
        float(game["gols_sofridos"])
        for game in finished
    )

    points = (
        wins * 3
        + draws
    )

    return {
        "disponivel": True,
        "time_id": bucket.get("time_id"),
        "time": bucket.get("nome"),
        "jogos_analisados": len(games),
        "jogos_com_placar": games_with_score,
        "vitorias": wins,
        "empates": draws,
        "derrotas": losses,
        "pontos": points,
        "aproveitamento": (
            round(
                points
                / (games_with_score * 3)
                * 100,
                2,
            )
            if games_with_score
            else None
        ),
        "gols_feitos": goals_for,
        "gols_sofridos": goals_against,
        "media_gols_feitos": (
            round(
                goals_for / games_with_score,
                2,
            )
            if games_with_score
            else None
        ),
        "media_gols_sofridos": (
            round(
                goals_against / games_with_score,
                2,
            )
            if games_with_score
            else None
        ),
        "medias_estatisticas": {
            metric: average(metric)
            for metric in STAT_ALIASES
        },
        "ultimas_partidas": games,
    }


def build_match_analyst_input(
    cache,
    home_ref,
    away_ref,
    recent_games=10,
):
    """
    Prepara uma entrada única para os dois analistas.

    IMPORTANTE:
    sem chamada à API.
    """

    home = summarize_team_history(
        cache,
        home_ref,
        recent_games,
    )

    away = summarize_team_history(
        cache,
        away_ref,
        recent_games,
    )

    return {
        "fonte": "partidas_enriquecidas",
        "sem_nova_chamada_api": True,
        "janela": recent_games,
        "casa": home,
        "fora": away,
        "historico_disponivel": bool(
            home.get("disponivel")
            and away.get("disponivel")
        ),
    }
