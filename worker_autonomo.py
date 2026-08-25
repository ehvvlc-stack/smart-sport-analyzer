import os
import time
import base64
from io import StringIO
from datetime import datetime

import pandas as pd
import requests

SPORTMONKS_TOKEN = os.getenv("SPORTMONKS_TOKEN", "").strip()
APIFOOTBALL_KEY = os.getenv("APIFOOTBALL_KEY", "").strip()
APIFOOTBALL_INTERVALO_SEGUNDOS = int(
    os.getenv("APIFOOTBALL_INTERVALO_SEGUNDOS", "2400")
)
APIFOOTBALL_RESERVA_DIA = int(
    os.getenv("APIFOOTBALL_RESERVA_DIA", "10")
)
APIFOOTBALL_PATH = os.getenv(
    "APIFOOTBALL_PATH",
    "data/monitoramento_apifootball.csv"
).strip()
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
GITHUB_REPO = os.getenv("GITHUB_REPO", "ehvvlc-stack/smart-sport-analyzer").strip()
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main").strip()
GITHUB_MONITORAMENTO_PATH = os.getenv(
    "GITHUB_MONITORAMENTO_PATH",
    "data/monitoramento_oportunidades.csv"
).strip()
ARQUIVO_VALIDACAO = "data/validacao_alertas.csv"

COLUNAS_VALIDACAO = [
    "id_alerta",
    "data_hora_alerta",
    "fixture_id",
    "jogo",
    "minuto_alerta",
    "placar_alerta",
    "time_destaque",
    "indice_alerta",
    "momento_10_min",
    "qualidade_score",
    "qualidade_nivel",
    "gol_ate_5_min",
    "gol_ate_10_min",
    "time_gol",
    "minuto_gol",
    "minutos_apos_alerta",
    "resultado_gol",
    "gol_time_destaque_5_min",
    "gol_time_destaque_10_min",
    "escanteio_ate_5_min",
    "escanteio_ate_10_min",
    "escanteio_time_destaque_5_min",
    "escanteio_time_destaque_10_min",
    "primeiro_escanteio_time",
    "primeiro_escanteio_minuto",
    "minutos_ate_escanteio",
    "status",
]
INTERVALO_SEGUNDOS = int(os.getenv("INTERVALO_SEGUNDOS", "60"))
BASE_URL = "https://api.sportmonks.com/v3/football"

LIGAS = {
    271: "Superliga",
    501: "Premiership",
    513: "Premiership Play-Offs",
    1659: "Superliga Play-offs",
}

COLUNAS_MONITORAMENTO = [
    "id_snapshot", "data_hora", "fixture_id", "jogo", "minuto",
    "bucket_5min", "placar", "nivel", "time_destaque",
    "indice_destaque", "diferenca", "momento_destaque",
    "posse_destaque", "vantagem_corners", "status_monitoramento",
    "data_hora_finalizacao", "placar_final", "placar_final_origem",
    "qualidade_dados", "cobertura_dados", "campos_faltantes",
    "eventos_disponiveis",
]

def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)

def requisicao(url, params):
    try:
        r = requests.get(url, params=params, timeout=25)
        if r.status_code != 200:
            return None, r.status_code
        return r.json(), 200
    except requests.RequestException:
        return None, -1

def buscar_fixture(fixture_id):
    dados, status = requisicao(
        f"{BASE_URL}/fixtures/{fixture_id}",
        {
            "api_token": SPORTMONKS_TOKEN,
            "include": "participants;scores;statistics.type;state;events.type",
        },
    )
    if status != 200:
        return None
    return dados.get("data", {})
def buscar_jogos_live():
    dados, status = requisicao(
        f"{BASE_URL}/livescores/inplay",
        {
            "api_token": SPORTMONKS_TOKEN,
            "include": "participants;state",
        },
    )

    if status != 200:
        return [], status

    todos_live = dados.get("data", []) or []

    lives = [
        jogo for jogo in todos_live
        if jogo.get("league_id") in LIGAS
    ]

    log(
        f"SportMonks inplay: {len(todos_live)} recebidos • "
        f"{len(lives)} nas ligas monitoradas"
    )

    completos = []

    for live in lives:
        fixture_id = live.get("id")

        if fixture_id is None:
            continue

        jogo = buscar_fixture(fixture_id)

        if jogo:
            completos.append(jogo)

    return completos, 200



def apifootball_headers():
    return {
        "x-apisports-key": APIFOOTBALL_KEY
    }


def apifootball_get(endpoint, params=None):
    if not APIFOOTBALL_KEY:
        return None, 0

    url = (
        "https://v3.football.api-sports.io/"
        + endpoint.lstrip("/")
    )

    try:
        r = requests.get(
            url,
            headers=apifootball_headers(),
            params=params or {},
            timeout=25
        )

        restante = r.headers.get(
            "x-ratelimit-requests-remaining"
        )

        try:
            restante = int(restante)
        except Exception:
            restante = -1

        if r.status_code != 200:
            log(
                f"API-Football status {r.status_code}: {r.text[:500]}"
            )
            return None, restante

        return r.json(), restante

    except requests.RequestException as exc:
        log(
            f"API-Football erro de rede: {exc}"
        )
        return None, -1


def ler_csv_github_generico(caminho, colunas):
    url = (
        f"https://api.github.com/repos/"
        f"{GITHUB_REPO}/contents/{caminho}"
    )

    try:
        r = requests.get(
            url,
            headers=gh_headers(),
            params={"ref": GITHUB_BRANCH},
            timeout=20
        )

        if r.status_code == 404:
            return pd.DataFrame(
                columns=colunas
            )

        if r.status_code != 200:
            log(
                f"Falha ao ler {caminho}: "
                f"{r.status_code}"
            )
            return pd.DataFrame(
                columns=colunas
            )

        texto = base64.b64decode(
            r.json().get("content", "")
        ).decode(
            "utf-8-sig"
        )

        df = pd.read_csv(
            StringIO(texto)
        )

    except Exception as exc:
        log(
            f"Erro ao ler {caminho}: {exc}"
        )
        return pd.DataFrame(
            columns=colunas
        )

    for coluna in colunas:
        if coluna not in df.columns:
            df[coluna] = ""

    return df[colunas]


def salvar_csv_github_generico(
    caminho,
    df,
    mensagem
):
    url = (
        f"https://api.github.com/repos/"
        f"{GITHUB_REPO}/contents/{caminho}"
    )

    sha = None

    try:
        atual = requests.get(
            url,
            headers=gh_headers(),
            params={"ref": GITHUB_BRANCH},
            timeout=20
        )

        if atual.status_code == 200:
            sha = atual.json().get("sha")

        payload = {
            "message": mensagem,
            "content": base64.b64encode(
                df.to_csv(
                    index=False
                ).encode("utf-8")
            ).decode("ascii"),
            "branch": GITHUB_BRANCH,
        }

        if sha:
            payload["sha"] = sha

        r = requests.put(
            url,
            headers=gh_headers(),
            json=payload,
            timeout=25
        )

        if r.status_code not in (
            200,
            201
        ):
            log(
                f"Falha ao salvar {caminho}: "
                f"{r.status_code}"
            )
            return False

        return True

    except Exception as exc:
        log(
            f"Erro ao salvar {caminho}: {exc}"
        )
        return False


COLUNAS_APIFOOTBALL = [
    "data_hora",
    "fixture_id",
    "liga",
    "pais",
    "jogo",
    "minuto",
    "placar",
    "status",
    "posse_casa",
    "posse_fora",
    "corners_casa",
    "corners_fora",
    "chutes_gol_casa",
    "chutes_gol_fora",
    "chutes_total_casa",
    "chutes_total_fora",
    "amarelos_casa",
    "amarelos_fora",
    "vermelhos_casa",
    "vermelhos_fora",
    "qualidade_coleta",
    "quota_restante",
]


def normalizar_numero_apifootball(valor):
    if valor is None:
        return None

    if isinstance(valor, str):
        valor = valor.replace(
            "%",
            ""
        ).strip()

    try:
        return float(valor)
    except Exception:
        return None


def extrair_stats_apifootball(resposta):
    saida = {
        "home": {},
        "away": {},
    }

    times = (
        resposta.get(
            "response",
            []
        )
        if resposta
        else []
    )

    for idx, bloco in enumerate(times[:2]):
        lado = (
            "home"
            if idx == 0
            else "away"
        )

        for item in bloco.get(
            "statistics",
            []
        ) or []:
            tipo = str(
                item.get(
                    "type",
                    ""
                )
            ).strip().lower()

            valor = normalizar_numero_apifootball(
                item.get(
                    "value"
                )
            )

            saida[lado][tipo] = valor

    return saida


def stat_af(stats, lado, nomes):
    mapa = stats.get(
        lado,
        {}
    )

    for nome in nomes:
        chave = nome.lower()
        if chave in mapa:
            return mapa.get(chave)

    return None


def ciclo_apifootball():
    """
    Coleta experimental e separada da API-Football.

    Conservador por causa do plano gratuito de 100 req/dia:
    - roda, por padrão, a cada 40 min;
    - 1 chamada para descobrir jogos ao vivo;
    - no máximo 1 chamada adicional de estatísticas por ciclo;
    - para quando a quota restante chega à reserva configurada.

    Não mistura estes dados com os sinais SportMonks.
    Salva em data/monitoramento_apifootball.csv.
    """
    if not APIFOOTBALL_KEY:
        log(
            "API-Football: chave ausente, "
            "coleta complementar desativada"
        )
        return

    dados, restante = apifootball_get(
        "fixtures",
        {"live": "all"}
    )
log(
    "API-Football resposta: "
    f"results={dados.get('results') if isinstance(dados, dict) else 'n/a'} • "
    f"errors={dados.get('errors') if isinstance(dados, dict) else 'n/a'}"
)
    if dados is None:
        return

    if (
        restante >= 0
        and restante <= APIFOOTBALL_RESERVA_DIA
    ):
        log(
            "API-Football: reserva diária atingida "
            f"({restante} restantes)"
        )
        return

    jogos = dados.get(
        "response",
        []
    ) or []

    if not jogos:
        log(
            "API-Football: 0 jogos ao vivo • "
            f"quota restante {restante}"
        )
        return

    # Por segurança de quota, detalhamos apenas 1 jogo por ciclo.
    jogo = jogos[0]

    fixture = jogo.get(
        "fixture",
        {}
    ) or {}

    fixture_id = fixture.get(
        "id"
    )

    if fixture_id is None:
        return

    stats_resp, restante_stats = apifootball_get(
        "fixtures/statistics",
        {"fixture": fixture_id}
    )

    if stats_resp is None:
        return

    restante_final = (
        restante_stats
        if restante_stats >= 0
        else restante
    )

    times = jogo.get(
        "teams",
        {}
    ) or {}

    home_name = (
        times.get(
            "home",
            {}
        ) or {}
    ).get(
        "name",
        "Casa"
    )

    away_name = (
        times.get(
            "away",
            {}
        ) or {}
    ).get(
        "name",
        "Visitante"
    )

    goals = jogo.get(
        "goals",
        {}
    ) or {}

    status = fixture.get(
        "status",
        {}
    ) or {}

    minuto = status.get(
        "elapsed"
    )

    stats = extrair_stats_apifootball(
        stats_resp
    )

    posse_h = stat_af(
        stats,
        "home",
        ["Ball Possession"]
    )
    posse_a = stat_af(
        stats,
        "away",
        ["Ball Possession"]
    )

    corners_h = stat_af(
        stats,
        "home",
        ["Corner Kicks"]
    )
    corners_a = stat_af(
        stats,
        "away",
        ["Corner Kicks"]
    )

    sog_h = stat_af(
        stats,
        "home",
        ["Shots on Goal"]
    )
    sog_a = stat_af(
        stats,
        "away",
        ["Shots on Goal"]
    )

    shots_h = stat_af(
        stats,
        "home",
        ["Total Shots"]
    )
    shots_a = stat_af(
        stats,
        "away",
        ["Total Shots"]
    )

    yellow_h = stat_af(
        stats,
        "home",
        ["Yellow Cards"]
    )
    yellow_a = stat_af(
        stats,
        "away",
        ["Yellow Cards"]
    )

    red_h = stat_af(
        stats,
        "home",
        ["Red Cards"]
    )
    red_a = stat_af(
        stats,
        "away",
        ["Red Cards"]
    )

    essenciais = [
        posse_h,
        posse_a,
        corners_h,
        corners_a,
        sog_h,
        sog_a,
    ]

    presentes = sum(
        1
        for valor in essenciais
        if valor is not None
    )

    cobertura = (
        presentes
        / len(essenciais)
        * 100
    )

    if cobertura >= 83:
        qualidade = "ALTA"
    elif cobertura >= 50:
        qualidade = "MEDIA"
    else:
        qualidade = "INSUFICIENTE"

    league = jogo.get(
        "league",
        {}
    ) or {}

    linha = {
        "data_hora": datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
        "fixture_id": fixture_id,
        "liga": league.get(
            "name",
            ""
        ),
        "pais": league.get(
            "country",
            ""
        ),
        "jogo": (
            f"{home_name} x {away_name}"
        ),
        "minuto": minuto,
        "placar": (
            f"{goals.get('home', 0)} x "
            f"{goals.get('away', 0)}"
        ),
        "status": status.get(
            "short",
            ""
        ),
        "posse_casa": posse_h,
        "posse_fora": posse_a,
        "corners_casa": corners_h,
        "corners_fora": corners_a,
        "chutes_gol_casa": sog_h,
        "chutes_gol_fora": sog_a,
        "chutes_total_casa": shots_h,
        "chutes_total_fora": shots_a,
        "amarelos_casa": yellow_h,
        "amarelos_fora": yellow_a,
        "vermelhos_casa": red_h,
        "vermelhos_fora": red_a,
        "qualidade_coleta": qualidade,
        "quota_restante": restante_final,
    }

    df = ler_csv_github_generico(
        APIFOOTBALL_PATH,
        COLUNAS_APIFOOTBALL
    )

    # Evita duplicar exatamente o mesmo jogo/minuto.
    if not df.empty:
        mascara = (
            df["fixture_id"]
            .astype(str)
            .eq(str(fixture_id))
            &
            df["minuto"]
            .astype(str)
            .eq(str(minuto))
        )
    else:
        mascara = pd.Series(
            dtype=bool
        )

    if (
        not df.empty
        and mascara.any()
    ):
        idx = df.index[
            mascara
        ][-1]

        for chave, valor in linha.items():
            df.at[
                idx,
                chave
            ] = valor
    else:
        df = pd.concat(
            [
                df,
                pd.DataFrame(
                    [linha]
                )
            ],
            ignore_index=True
        )

    ok = salvar_csv_github_generico(
        APIFOOTBALL_PATH,
        df,
        "Atualiza coleta experimental API-Football"
    )

    log(
        "API-Football: "
        f"{len(jogos)} ao vivo • "
        f"capturado {home_name} x {away_name} "
        f"min {minuto} • dados {qualidade} • "
        f"quota {restante_final} • "
        f"GitHub {'OK' if ok else 'FALHOU'}"
    )


def identificar_times(jogo):
    casa, visitante = "Casa", "Visitante"
    ids = {"home": None, "away": None}
    nomes = {}

    for p in jogo.get("participants", []) or []:
        pid = p.get("id")
        nome = p.get("name", "Time")
        nomes[pid] = nome
        local = (p.get("meta", {}) or {}).get("location")
        if local == "home":
            casa, ids["home"] = nome, pid
        elif local == "away":
            visitante, ids["away"] = nome, pid

    return casa, visitante, ids, nomes

def placar_atual(jogo):
    gh = ga = 0
    for placar in jogo.get("scores", []) or []:
        if placar.get("description") != "CURRENT":
            continue
        score = placar.get("score", {}) or {}
        lado = score.get("participant")
        if lado == "home":
            gh = score.get("goals", 0)
        elif lado == "away":
            ga = score.get("goals", 0)
    return gh, ga

def ler_estatisticas(jogo, ids):
    campos = ["possession", "corners", "dribbles", "yellow", "red"]
    dados = {
        "home": {c: 0 for c in campos},
        "away": {c: 0 for c in campos},
        "_presentes": {
            "home": {c: False for c in campos},
            "away": {c: False for c in campos},
        },
    }

    for item in jogo.get("statistics", []) or []:
        pid = item.get("participant_id")
        if pid == ids["home"]:
            lado = "home"
        elif pid == ids["away"]:
            lado = "away"
        else:
            continue

        tipo = str((item.get("type", {}) or {}).get("name", "")).strip().lower()
        bruto = (item.get("data", {}) or {}).get("value", None)
        if bruto is None:
            continue
        try:
            valor = float(bruto)
        except (TypeError, ValueError):
            continue

        if "corner" in tipo or "escanteio" in tipo:
            dados[lado]["corners"] = valor
            dados["_presentes"][lado]["corners"] = True
        elif "possession" in tipo or "posse" in tipo:
            dados[lado]["possession"] = valor
            dados["_presentes"][lado]["possession"] = True
        elif "successful dribble" in tipo or "drible" in tipo:
            dados[lado]["dribbles"] = valor
            dados["_presentes"][lado]["dribbles"] = True
        elif (
            "yellowred" in tipo or "yellow-red" in tipo
            or "redcard" in tipo or "red card" in tipo
            or "cartÃ£o vermelho" in tipo
        ):
            dados[lado]["red"] += valor
            dados["_presentes"][lado]["red"] = True
        elif (
            "yellowcard" in tipo or "yellow card" in tipo
            or "cartÃ£o amarelo" in tipo
        ):
            dados[lado]["yellow"] = valor
            dados["_presentes"][lado]["yellow"] = True

    return dados

def avaliar_qualidade_dados(jogo, stats, minuto):
    presentes = stats.get("_presentes", {})
    essenciais = ["possession", "corners", "dribbles"]
    total = len(essenciais) * 2
    encontrados = sum(
        1
        for lado in ["home", "away"]
        for campo in essenciais
        if presentes.get(lado, {}).get(campo, False)
    )
    cobertura = encontrados / total * 100 if total else 0.0
    faltantes = [
        f"{lado}.{campo}"
        for lado in ["home", "away"]
        for campo in essenciais
        if not presentes.get(lado, {}).get(campo, False)
    ]
    eventos = jogo.get("events", []) or []

    if minuto is None:
        nivel = "INSUFICIENTE"
    elif cobertura >= 83:
        nivel = "ALTA"
    elif cobertura >= 50:
        nivel = "MÃ‰DIA"
    else:
        nivel = "INSUFICIENTE"

    return {
        "nivel": nivel,
        "cobertura": round(cobertura, 1),
        "faltantes": faltantes,
        "quantidade_eventos": len(eventos),
    }

def participacao(a, b):
    total = a + b
    return 50.0 if total <= 0 else (a / total) * 100

def calcular_indice(home, away):
    posse_h = participacao(home["possession"], away["possession"])
    posse_a = 100 - posse_h
    corners_h = participacao(home["corners"], away["corners"])
    corners_a = 100 - corners_h
    dribles_h = participacao(home["dribbles"], away["dribbles"])
    dribles_a = 100 - dribles_h

    disciplina_h = max(0, 100 - home["yellow"] * 2 - home["red"] * 12)
    disciplina_a = max(0, 100 - away["yellow"] * 2 - away["red"] * 12)

    bruto_h = posse_h * 0.35 + corners_h * 0.35 + dribles_h * 0.20 + disciplina_h * 0.10
    bruto_a = posse_a * 0.35 + corners_a * 0.35 + dribles_a * 0.20 + disciplina_a * 0.10

    total = bruto_h + bruto_a
    if total <= 0:
        return 50.0, 50.0

    ih = (bruto_h / total) * 100
    return round(ih, 1), round(100 - ih, 1)

def preparar_eventos(jogo, nomes_por_id):
    linhas = []
    for evento in jogo.get("events", []) or []:
        minuto = evento.get("minute", 0) or 0
        pid = evento.get("participant_id")
        time_nome = nomes_por_id.get(pid, "Sem time")
        tipo = (
            (evento.get("type", {}) or {}).get("name")
            if isinstance(evento.get("type"), dict)
            else None
        )
        if not tipo:
            tipo = evento.get("addition", "Evento")
        linhas.append({"minuto_num": minuto, "Time": time_nome, "Evento": tipo})
    linhas.sort(key=lambda x: x["minuto_num"])
    return linhas
def revisar_validacoes_pendentes_worker():
    df = ler_validacoes_github()

    if df.empty:
        return False

    colunas_texto = [
        "gol_ate_5_min",
        "gol_ate_10_min",
        "time_gol",
        "resultado_gol",
        "gol_time_destaque_5_min",
        "gol_time_destaque_10_min",
        "status",
    ]

    for coluna in colunas_texto:
        if coluna in df.columns:
            df[coluna] = df[coluna].astype("object")

    pendentes = df.index[
        df["status"].astype(str) == "ACOMPANHANDO"
    ].tolist()

    if not pendentes:
        return False

    alterou = False
    cache_jogos = {}

    for idx in pendentes:
        try:
            fixture_id = int(
                float(df.at[idx, "fixture_id"])
            )

            minuto_alerta = int(
                float(df.at[idx, "minuto_alerta"])
            )

            time_destaque = str(
                df.at[idx, "time_destaque"]
            )

            if fixture_id not in cache_jogos:
                cache_jogos[fixture_id] = buscar_fixture(
                    fixture_id
                )

            jogo = cache_jogos[fixture_id]

            if not jogo:
                continue

            casa, visitante, ids, nomes = identificar_times(jogo)

            eventos = preparar_eventos(
                jogo,
                nomes
            )

            minuto_atual = minuto_estimado(jogo)

            gols_depois = []

            for evento in eventos:
                nome = str(
                    evento.get("Evento", "")
                ).lower()

                if "goal" not in nome:
                    continue

                try:
                    minuto_evento = int(
                        evento.get(
                            "minuto_num",
                            0
                        ) or 0
                    )
                except Exception:
                    continue

                if (
                    minuto_alerta
                    < minuto_evento
                    <= minuto_alerta + 10
                ):
                    gols_depois.append(evento)

            gols_depois.sort(
                key=lambda e: int(
                    e.get(
                        "minuto_num",
                        999
                    ) or 999
                )
            )

            if gols_depois:
                primeiro_gol = gols_depois[0]

                minuto_gol = int(
                    primeiro_gol.get(
                        "minuto_num",
                        0
                    )
                )

                time_gol = str(
                    primeiro_gol.get(
                        "Time",
                        ""
                    )
                )

                delta = (
                    minuto_gol
                    - minuto_alerta
                )

                marcou_destaque = (
                    time_gol
                    == time_destaque
                )

                df.at[idx, "time_gol"] = time_gol
                df.at[idx, "minuto_gol"] = minuto_gol
                df.at[idx, "minutos_apos_alerta"] = delta

                df.at[idx, "resultado_gol"] = (
                    "TIME_DESTAQUE"
                    if marcou_destaque
                    else "ADVERSARIO"
                )

                if delta <= 5:
                    df.at[idx, "gol_ate_5_min"] = "SIM"
                    df.at[idx, "gol_time_destaque_5_min"] = (
                        "SIM"
                        if marcou_destaque
                        else "NÃO"
                    )
                else:
                    df.at[idx, "gol_ate_5_min"] = "NÃO"
                    df.at[idx, "gol_time_destaque_5_min"] = "NÃO"

                df.at[idx, "gol_ate_10_min"] = "SIM"

                df.at[idx, "gol_time_destaque_10_min"] = (
                    "SIM"
                    if marcou_destaque
                    else "NÃO"
                )

                df.at[idx, "status"] = "ENCERRADO_COM_GOL"

                alterou = True

            elif (
                minuto_atual is not None
                and minuto_atual >= minuto_alerta + 10
            ):
                df.at[idx, "gol_ate_5_min"] = "NÃO"
                df.at[idx, "gol_ate_10_min"] = "NÃO"
                df.at[idx, "gol_time_destaque_5_min"] = "NÃO"
                df.at[idx, "gol_time_destaque_10_min"] = "NÃO"
                df.at[idx, "resultado_gol"] = "SEM_GOL"
                df.at[idx, "status"] = "ENCERRADO_SEM_GOL"

                alterou = True

        except Exception as erro:
            log(
                f"Erro ao revisar validação pendente "
                f"{idx}: {erro}"
            )

    if alterou:
        ok = salvar_validacoes_github(df)

        log(
            "Validações pendentes: "
            + ("atualizadas" if ok else "falha ao salvar")
        )

        return ok

    return False

def pontuar_evento(evento):
    nome = str(evento["Evento"]).lower()
    if "goal" in nome:
        return 8
    if "red" in nome:
        return -6
    if "yellow" in nome:
        return -2
    if "substitution" in nome:
        return 1
    return 1

def pressao_eventos(eventos, minuto_atual, casa, visitante, janela=10):
    inicio = max(0, minuto_atual - janela)
    recentes = [e for e in eventos if inicio < e["minuto_num"] <= minuto_atual]
    pc = pv = 0
    for e in recentes:
        pontos = pontuar_evento(e)
        if e["Time"] == casa:
            pc += pontos
        elif e["Time"] == visitante:
            pv += pontos
    pc2, pv2 = max(0, pc), max(0, pv)
    soma = pc2 + pv2
    if soma == 0:
        ic, iv = 50.0, 50.0
    else:
        ic = (pc2 / soma) * 100
        iv = 100 - ic
    return {"indice_casa": round(ic, 1), "indice_visitante": round(iv, 1)}

def minuto_estimado(jogo):
    estado = jogo.get("state", {}) or {}
    candidatos = []
    clock = estado.get("clock")
    if isinstance(clock, dict):
        candidatos.extend([clock.get("minute"), clock.get("minutes")])
    else:
        candidatos.append(clock)
    candidatos.extend([estado.get("minute"), estado.get("minutes")])

    for valor in candidatos:
        try:
            minuto = int(float(valor))
            if 0 <= minuto <= 130:
                return minuto
        except Exception:
            pass

    minutos_eventos = []
    for e in jogo.get("events", []) or []:
        try:
            m = int(float(e.get("minute", 0) or 0))
            if 0 <= m <= 130:
                minutos_eventos.append(m)
        except Exception:
            pass
    if minutos_eventos:
        return max(minutos_eventos)

    inicio = jogo.get("starting_at")
    if inicio:
        try:
            inicio_dt = pd.to_datetime(inicio, utc=True)
            agora_utc = pd.Timestamp.now(tz="UTC")
            corridos = (agora_utc - inicio_dt).total_seconds() / 60
            estado_txt = " ".join([
                str(estado.get("name", "")),
                str(estado.get("short_name", "")),
            ]).lower()
            if "2nd" in estado_txt or "second" in estado_txt:
                corridos -= 15
            return int(max(0, min(90, corridos)))
        except Exception:
            pass
    return None

def combinar_indices(dh, da, mh, ma):
    ch = dh * 0.70 + mh * 0.30
    ca = da * 0.70 + ma * 0.30
    total = ch + ca
    if total <= 0:
        return 50.0, 50.0
    fh = (ch / total) * 100
    return round(fh, 1), round(100 - fh, 1)

def classificar_pressao_live(ch, ca, mh, ma, casa, visitante):
    if ch >= ca:
        dominante, momento = casa, mh
    else:
        dominante, momento = visitante, ma
    diferenca = abs(ch - ca)
    if diferenca >= 25 and momento >= 60:
        return "ALTA", dominante
    if diferenca >= 12 and momento >= 58:
        return "MODERADA", dominante
    return "BAIXA", dominante

def gh_headers():
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

def ler_monitoramento_github():
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_MONITORAMENTO_PATH}"
    try:
        r = requests.get(url, headers=gh_headers(), params={"ref": GITHUB_BRANCH}, timeout=20)
        if r.status_code == 404:
            return pd.DataFrame(columns=COLUNAS_MONITORAMENTO)
        if r.status_code != 200:
            log(f"Falha ao ler GitHub: {r.status_code}")
            return pd.DataFrame(columns=COLUNAS_MONITORAMENTO)
        texto = base64.b64decode(r.json().get("content", "")).decode("utf-8-sig")
        df = pd.read_csv(StringIO(texto))
    except Exception as exc:
        log(f"Erro ao ler GitHub: {exc}")
        return pd.DataFrame(columns=COLUNAS_MONITORAMENTO)

    for c in COLUNAS_MONITORAMENTO:
        if c not in df.columns:
            df[c] = ""
    return df[COLUNAS_MONITORAMENTO]

def ler_validacoes_github():
    return ler_csv_github_generico(
        ARQUIVO_VALIDACAO,
        COLUNAS_VALIDACAO
    )


def salvar_validacoes_github(df):
    return salvar_csv_github_generico(
        ARQUIVO_VALIDACAO,
        df,
        "Atualiza validação automática"
    )

def salvar_monitoramento_github(df):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_MONITORAMENTO_PATH}"
    sha = None
    try:
        atual = requests.get(url, headers=gh_headers(), params={"ref": GITHUB_BRANCH}, timeout=20)
        if atual.status_code == 200:
            sha = atual.json().get("sha")

        payload = {
            "message": "Atualiza monitoramento autÃ´nomo",
            "content": base64.b64encode(df.to_csv(index=False).encode("utf-8")).decode("ascii"),
            "branch": GITHUB_BRANCH,
        }
        if sha:
            payload["sha"] = sha

        r = requests.put(url, headers=gh_headers(), json=payload, timeout=25)
        if r.status_code not in (200, 201):
            log(f"Falha ao salvar GitHub: {r.status_code} {r.text[:200]}")
            return False
        return True
    except Exception as exc:
        log(f"Erro ao salvar GitHub: {exc}")
        return False

def atualizar_snapshot(df, jogo):
    casa, visitante, ids, nomes = identificar_times(jogo)
    fixture_id = jogo.get("id")
    gh, ga = placar_atual(jogo)
    stats = ler_estatisticas(jogo, ids)
    minuto = minuto_estimado(jogo)
    if minuto is None:
        return df, False, "sem minuto"

    qualidade = avaliar_qualidade_dados(jogo, stats, minuto)
    if qualidade["nivel"] == "INSUFICIENTE":
        return df, False, "dados insuficientes"

    home, away = stats["home"], stats["away"]
    dh, da = calcular_indice(home, away)
    eventos = preparar_eventos(jogo, nomes)
    momento = pressao_eventos(eventos, minuto, casa, visitante, janela=10)
    ch, ca = combinar_indices(dh, da, momento["indice_casa"], momento["indice_visitante"])
    nivel, dominante = classificar_pressao_live(
        ch, ca, momento["indice_casa"], momento["indice_visitante"], casa, visitante
    )

    if ch >= ca:
        indice = ch
        momento_destaque = momento["indice_casa"]
        posse = home["possession"]
        vantagem_corners = home["corners"] - away["corners"]
    else:
        indice = ca
        momento_destaque = momento["indice_visitante"]
        posse = away["possession"]
        vantagem_corners = away["corners"] - home["corners"]

    minuto_int = int(minuto)
    bucket = minuto_int // 5
    id_snapshot = f"{fixture_id}-{bucket}"

    linha = {
        "id_snapshot": id_snapshot,
        "data_hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "fixture_id": fixture_id,
        "jogo": f"{casa} x {visitante}",
        "minuto": minuto_int,
        "bucket_5min": bucket,
        "placar": f"{gh} x {ga}",
        "nivel": nivel,
        "time_destaque": dominante,
        "indice_destaque": round(float(indice), 1),
        "diferenca": round(abs(float(ch) - float(ca)), 1),
        "momento_destaque": round(float(momento_destaque), 1),
        "posse_destaque": round(float(posse), 1),
        "vantagem_corners": round(float(vantagem_corners), 1),
        "status_monitoramento": "AO_VIVO",
        "data_hora_finalizacao": "",
        "placar_final": "",
        "placar_final_origem": "",
        "qualidade_dados": qualidade["nivel"],
        "cobertura_dados": qualidade["cobertura"],
        "campos_faltantes": ", ".join(qualidade["faltantes"]),
        "eventos_disponiveis": qualidade["quantidade_eventos"],
    }

    mascara = (
        df["id_snapshot"].astype(str).eq(id_snapshot)
        if not df.empty else pd.Series(dtype=bool)
    )
    if not df.empty and mascara.any():
        idx = df.index[mascara][-1]
        for k, v in linha.items():
            df.at[idx, k] = v
    else:
        df = pd.concat([df, pd.DataFrame([linha])], ignore_index=True)

    return df, True, nivel

def finalizar_desaparecidos(df, ativos):
    if df.empty:
        return df, False
    ativos = {str(x) for x in ativos if x is not None}
    alterou = False
    agora = datetime.now()

    for fixture in df["fixture_id"].astype(str).unique().tolist():
        if fixture in ativos:
            continue

        mascara = df["fixture_id"].astype(str).eq(fixture)
        jogo_df = df[mascara].copy()
        tempos = pd.to_datetime(jogo_df["data_hora"], errors="coerce")
        if not tempos.notna().any():
            continue

        idx_ultimo = tempos.idxmax()
        ultimo_horario = tempos.loc[idx_ultimo]

        if str(df.at[idx_ultimo, "status_monitoramento"]) == "FINALIZADO":
            continue

        minuto = pd.to_numeric(
            pd.Series([df.at[idx_ultimo, "minuto"]]),
            errors="coerce"
        ).iloc[0]
        sem_ver = (agora - ultimo_horario.to_pydatetime()).total_seconds() / 60

        deve = (
            (pd.notna(minuto) and float(minuto) >= 85 and sem_ver >= 5)
            or sem_ver >= 25
        )
        if not deve:
            continue

        df.loc[mascara, "status_monitoramento"] = "FINALIZADO"
        df.loc[mascara, "data_hora_finalizacao"] = agora.strftime("%Y-%m-%d %H:%M:%S")

        placar_ultimo = str(df.at[idx_ultimo, "placar"])
        placar_final_atual = str(df.at[idx_ultimo, "placar_final"]).strip()
        if not placar_final_atual or placar_final_atual.lower() in {"nan", "none"}:
            df.loc[mascara, "placar_final"] = placar_ultimo
            df.loc[mascara, "placar_final_origem"] = "ULTIMO_OBSERVADO"

        alterou = True

    return df, alterou

def validar_ambiente():
    faltantes = []
    if not SPORTMONKS_TOKEN:
        faltantes.append("SPORTMONKS_TOKEN")
    if not GITHUB_TOKEN:
        faltantes.append("GITHUB_TOKEN")
    if not GITHUB_REPO:
        faltantes.append("GITHUB_REPO")
    if faltantes:
        raise RuntimeError("VariÃ¡veis ausentes: " + ", ".join(faltantes))

def ciclo():
    df = ler_monitoramento_github()
    jogos, status = buscar_jogos_live()
    if status != 200:
        log(f"SportMonks status {status}")
        return

    ativos = [jogo.get("id") for jogo in jogos]
    alterou = False
    processados = 0
    bloqueados = 0

    for jogo in jogos:
        try:
            df, mudou, detalhe = atualizar_snapshot(df, jogo)
            if mudou:
                alterou = True
                processados += 1
            else:
                bloqueados += 1
                log(f"Fixture {jogo.get('id')}: {detalhe}")
        except Exception as exc:
            log(f"Erro fixture {jogo.get('id')}: {exc}")

    df, finalizou = finalizar_desaparecidos(df, ativos)
    alterou = alterou or finalizou

    if alterou:
        ok = salvar_monitoramento_github(df)
        log("PersistÃªncia GitHub: " + ("OK" if ok else "FALHOU"))
    revisar_validacoes_pendentes_worker()
    log(
        f"Varredura: {len(jogos)} ao vivo â€¢ "
        f"{processados} processados â€¢ {bloqueados} bloqueados"
    )

def main():
    validar_ambiente()

    log(
        "Coletor híbrido iniciado: "
        "SportMonks + API-Football experimental"
    )

    proxima_api_football = 0.0

    while True:
        inicio = time.time()

        try:
            ciclo()
        except Exception as exc:
            log(
                f"Erro geral SportMonks: {exc}"
            )

        agora = time.time()

        if (
            APIFOOTBALL_KEY
            and agora >= proxima_api_football
        ):
            try:
                ciclo_apifootball()
            except Exception as exc:
                log(
                    f"Erro geral API-Football: {exc}"
                )

            proxima_api_football = (
                time.time()
                + APIFOOTBALL_INTERVALO_SEGUNDOS
            )

        gasto = (
            time.time()
            - inicio
        )

        time.sleep(
            max(
                10,
                INTERVALO_SEGUNDOS - gasto
            )
        )

if __name__ == "__main__":
    main()
