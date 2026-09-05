import os
import time
import base64
from io import StringIO
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import requests

SPORTMONKS_TOKEN = os.getenv("SPORTMONKS_TOKEN", "").strip()
APIFOOTBALL_KEY = os.getenv("APIFOOTBALL_KEY", "").strip()
FOOTBALL_DATA_TOKEN = os.getenv("FOOTBALL_DATA_TOKEN", "").strip()
APIFOOTBALL_INTERVALO_SEGUNDOS = int(
    os.getenv("APIFOOTBALL_INTERVALO_SEGUNDOS", "2400")
)
APIFOOTBALL_CONFIRMACAO_SEGUNDOS = int(
    os.getenv("APIFOOTBALL_CONFIRMACAO_SEGUNDOS", "300")
)
APIFOOTBALL_RESERVA_DIA = int(
    os.getenv("APIFOOTBALL_RESERVA_DIA", "10")
)
APIFOOTBALL_MAX_JOGOS = int(
    os.getenv("APIFOOTBALL_MAX_JOGOS", "1")
)
APIFOOTBALL_LIGAS = {
    item.strip()
    for item in os.getenv("APIFOOTBALL_LIGAS", "").split(",")
    if item.strip()
}
APIFOOTBALL_PATH = os.getenv(
    "APIFOOTBALL_PATH",
    "data/monitoramento_apifootball.csv"
).strip()
APIFOOTBALL_VALIDACAO_PATH = os.getenv(
    "APIFOOTBALL_VALIDACAO_PATH",
    "data/validacao_apifootball.csv"
).strip()
RELATORIO_DIARIO_ATIVO = os.getenv("RELATORIO_DIARIO_ATIVO", "1").strip() == "1"
RELATORIO_DIARIO_HORA = int(os.getenv("RELATORIO_DIARIO_HORA", "20"))
RELATORIO_DIARIO_MINUTO = int(os.getenv("RELATORIO_DIARIO_MINUTO", "0"))
RELATORIO_DIARIO_FUSO = os.getenv(
    "RELATORIO_DIARIO_FUSO", "America/Manaus"
).strip()
RELATORIO_DIARIO_PATH = os.getenv(
    "RELATORIO_DIARIO_PATH", "data/status_relatorio_diario.csv"
).strip()
SENTINELA_ATIVA = os.getenv("SENTINELA_ATIVA", "1").strip() == "1"
SENTINELA_FALHAS_LIMITE = int(os.getenv("SENTINELA_FALHAS_LIMITE", "3"))
SENTINELA_COTA_AVISO = int(os.getenv("SENTINELA_COTA_AVISO", "20"))
SENTINELA_INATIVIDADE_SEGUNDOS = int(
    os.getenv("SENTINELA_INATIVIDADE_SEGUNDOS", "10800")
)

ESTADO_SENTINELA = {
    "api_football_falhas": 0,
    "api_football_alertado": False,
    "sportmonks_falhas": 0,
    "sportmonks_alertado": False,
    "github_falhas": 0,
    "github_alertado": False,
    "ultima_api_sucesso": time.time(),
    "inatividade_alertada": False,
    "cota_alertada_data": "",
}
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
GITHUB_REPO = os.getenv("GITHUB_REPO", "ehvvlc-stack/smart-sport-analyzer").strip()
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main").strip()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
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
    "mercado_simulado",
    "odd_simulada",
    "stake_simulada",
    "resultado_financeiro",
    "lucro_prejuizo",
    "status",
]
INTERVALO_SEGUNDOS = int(os.getenv("INTERVALO_SEGUNDOS", "300"))
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


def enviar_alerta_telegram(mensagem):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log("Telegram não configurado; alerta não enviado")
        return False

    try:
        resposta = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": mensagem,
            },
            timeout=20,
        )
        if resposta.status_code != 200:
            log(f"Falha Telegram: {resposta.status_code}")
            return False
        log("Alerta Telegram enviado")
        return True
    except requests.RequestException as exc:
        log(f"Erro Telegram: {exc}")
        return False


def sentinela_registrar(componente, sucesso, detalhe=""):
    if not SENTINELA_ATIVA:
        return
    chave = componente.lower().replace("-", "_").replace(" ", "_")
    chave_falhas = f"{chave}_falhas"
    chave_alertado = f"{chave}_alertado"
    if chave_falhas not in ESTADO_SENTINELA:
        return

    if sucesso:
        estava_alertado = ESTADO_SENTINELA[chave_alertado]
        ESTADO_SENTINELA[chave_falhas] = 0
        ESTADO_SENTINELA[chave_alertado] = False
        if componente == "api_football":
            ESTADO_SENTINELA["ultima_api_sucesso"] = time.time()
            if ESTADO_SENTINELA["inatividade_alertada"]:
                estava_alertado = True
                ESTADO_SENTINELA["inatividade_alertada"] = False
        if estava_alertado:
            enviar_alerta_telegram(
                "✅ SENTINELA — SERVIÇO RECUPERADO\n\n"
                f"🔧 Componente: {componente}\n"
                f"📡 Situação: voltou a funcionar normalmente.\n"
                f"📝 {detalhe or 'Nova operação concluída com sucesso.'}"
            )
        return

    ESTADO_SENTINELA[chave_falhas] += 1
    falhas = ESTADO_SENTINELA[chave_falhas]
    log(f"Sentinela: {componente} com {falhas} falha(s) consecutiva(s)")
    if falhas < max(1, SENTINELA_FALHAS_LIMITE):
        return
    if ESTADO_SENTINELA[chave_alertado]:
        return
    enviado = enviar_alerta_telegram(
        "🚨 SENTINELA — ATENÇÃO NECESSÁRIA\n\n"
        f"🔧 Componente: {componente}\n"
        f"❌ Falhas consecutivas: {falhas}\n"
        f"📝 {detalhe or 'A operação não foi concluída.'}\n\n"
        "O worker continua ativo e tentará novamente automaticamente."
    )
    if enviado:
        ESTADO_SENTINELA[chave_alertado] = True


def sentinela_verificar_cota(restante):
    if not SENTINELA_ATIVA or restante is None:
        return
    try:
        restante = int(restante)
    except (TypeError, ValueError):
        return
    if restante < 0:
        return
    hoje = datetime.now(timezone.utc).date().isoformat()
    if restante > SENTINELA_COTA_AVISO:
        return
    if ESTADO_SENTINELA["cota_alertada_data"] == hoje:
        return
    if enviar_alerta_telegram(
        "⚠️ SENTINELA — COTA API-FOOTBALL\n\n"
        f"🔋 Restam {restante} requisições hoje.\n"
        f"🛡 Reserva protegida: {APIFOOTBALL_RESERVA_DIA}.\n"
        "O sistema reduzirá a coleta antes de consumir a reserva."
    ):
        ESTADO_SENTINELA["cota_alertada_data"] = hoje


def sentinela_verificar_inatividade():
    if not SENTINELA_ATIVA or ESTADO_SENTINELA["inatividade_alertada"]:
        return
    segundos = time.time() - ESTADO_SENTINELA["ultima_api_sucesso"]
    if segundos < SENTINELA_INATIVIDADE_SEGUNDOS:
        return
    if enviar_alerta_telegram(
        "🚨 SENTINELA — COLETA SEM RESPOSTA\n\n"
        f"⏱ A API-Football está há aproximadamente {segundos / 3600:.1f} hora(s) "
        "sem uma resposta bem-sucedida.\n"
        "O worker continuará tentando automaticamente."
    ):
        ESTADO_SENTINELA["inatividade_alertada"] = True

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
def buscar_jogos_football_data():
    if not FOOTBALL_DATA_TOKEN:
        log("football-data.org: token ausente")
        return [], 0

    hoje = datetime.now(timezone.utc).date()
    fim = (pd.Timestamp(hoje) + pd.Timedelta(days=14)).date()

    url = "https://api.football-data.org/v4/competitions/BSA/matches"

    headers = {
        "X-Auth-Token": FOOTBALL_DATA_TOKEN
    }

    params = {
        "dateFrom": hoje.isoformat(),
        "dateTo": fim.isoformat(),
    }

    try:
        r = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=25,
        )

        if r.status_code != 200:
            log(
                f"football-data.org: status {r.status_code} "
                f"{r.text[:300]}"
            )
            return [], r.status_code

        dados = r.json()
        jogos = dados.get("matches", []) or []

        log(
            f"football-data.org: {len(jogos)} jogos "
            f"nos próximos 14 dias"
        )

        return jogos, 200

    except requests.RequestException as exc:
        log(f"football-data.org erro de rede: {exc}")
        return [], -1
def buscar_jogos_live():
    dados, status = requisicao(
        f"{BASE_URL}/livescores/inplay",
        {
            "api_token": SPORTMONKS_TOKEN,
            "include": "participants;scores;statistics.type;state;events.type",
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

    return lives, 200


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
    StringIO(texto),
    dtype=object
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

    return df[colunas].astype("object")


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
    conteudo_novo = df.to_csv(
        index=False
    ).encode("utf-8")

    try:
        atual = requests.get(
            url,
            headers=gh_headers(),
            params={"ref": GITHUB_BRANCH},
            timeout=20
        )

        if atual.status_code == 200:
            dados_atuais = atual.json()
            sha = dados_atuais.get("sha")

            conteudo_atual = base64.b64decode(
                dados_atuais.get("content", "")
            )

            if conteudo_atual == conteudo_novo:
                log(
                    f"Sem alterações em {caminho}; "
                    "commit ignorado"
                )
                return True

        payload = {
            "message": mensagem,
            "content": base64.b64encode(
                conteudo_novo
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
def salvar_agenda_football_data(jogos):
    linhas = []

    for partida in jogos:
        linhas.append({
            "fixture_id": partida.get("id"),
            "data_hora": partida.get("utcDate"),
            "status": partida.get("status"),
            "casa_id": (partida.get("homeTeam") or {}).get("id"),
            "casa": (partida.get("homeTeam") or {}).get("name"),
            "fora_id": (partida.get("awayTeam") or {}).get("id"),
            "fora": (partida.get("awayTeam") or {}).get("name"),
            "competicao": (partida.get("competition") or {}).get("name"),
            "rodada": partida.get("matchday"),
        })

    df_agenda = pd.DataFrame(linhas)

    return salvar_csv_github_generico(
        "data/agenda_football_data.csv",
        df_agenda,
        "Atualiza agenda football-data.org"
    )

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
    "indice_casa",
    "indice_fora",
    "momento_casa",
    "momento_fora",
    "nivel_pressao",
    "time_destaque",
    "indice_destaque",
    "diferenca",
    "dna_pressao",
    "dna_score",
    "dna_motivos",
    "acoes_recentes_destaque",
    "situacao_placar",
    "elegivel_telegram",
    "motivo_bloqueio",
    "prioridade_coleta",
    "motivo_prioridade",
    "rastreamento_id",
    "rastreamento_origem_minuto",
    "rastreamento_etapa",
    "curva_pressao",
    "variacao_indice",
    "confirmacao_telegram_enviada",
]

COLUNAS_VALIDACAO_APIFOOTBALL = [
    "id_alerta", "data_hora_alerta", "fixture_id", "jogo",
    "minuto_alerta", "placar_alerta", "time_destaque",
    "indice_alerta", "momento_10_min", "corners_alerta",
    "dna_pressao", "dna_score", "dna_motivos", "situacao_placar",
    "gol_ate_5_min", "gol_ate_10_min", "escanteio_ate_5_min",
    "escanteio_ate_10_min", "status",
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


def ciclo_apifootball_legado():
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


def numero_af(valor, padrao=0.0):
    try:
        if pd.isna(valor):
            return float(padrao)
        return float(valor)
    except (TypeError, ValueError):
        return float(padrao)


def indices_apifootball(valores):
    ph = participacao(valores["posse_casa"], valores["posse_fora"])
    ch = participacao(valores["corners_casa"], valores["corners_fora"])
    gh = participacao(valores["chutes_gol_casa"], valores["chutes_gol_fora"])
    th = participacao(valores["chutes_total_casa"], valores["chutes_total_fora"])
    bruto_h = ph * 0.25 + ch * 0.25 + gh * 0.30 + th * 0.20
    bruto_a = (100 - ph) * 0.25 + (100 - ch) * 0.25 + (100 - gh) * 0.30 + (100 - th) * 0.20
    total = bruto_h + bruto_a
    if total <= 0:
        return 50.0, 50.0
    casa = bruto_h / total * 100
    return round(casa, 1), round(100 - casa, 1)


def momento_apifootball(atual, anterior):
    if anterior is None:
        return 50.0, 50.0, False
    minuto_atual = int(numero_af(atual.get("minuto"), -1))
    minuto_anterior = int(numero_af(anterior.get("minuto"), -1))
    intervalo = minuto_atual - minuto_anterior
    if intervalo < 2 or intervalo > 15:
        return 50.0, 50.0, False

    def delta(campo):
        return max(0.0, numero_af(atual.get(campo)) - numero_af(anterior.get(campo)))

    pontos_h = (
        delta("corners_casa") * 3
        + delta("chutes_gol_casa") * 4
        + delta("chutes_total_casa")
    )
    pontos_a = (
        delta("corners_fora") * 3
        + delta("chutes_gol_fora") * 4
        + delta("chutes_total_fora")
    )
    total = pontos_h + pontos_a
    if total <= 0:
        return 50.0, 50.0, True
    casa = pontos_h / total * 100
    return round(casa, 1), round(100 - casa, 1), True


def ultimo_snapshot_af(df, fixture_id, minuto):
    if df.empty:
        return None
    candidatos = df[df["fixture_id"].astype(str).eq(str(fixture_id))].copy()
    candidatos["_minuto"] = pd.to_numeric(candidatos["minuto"], errors="coerce")
    candidatos = candidatos[candidatos["_minuto"] < int(minuto)]
    if candidatos.empty:
        return None
    return candidatos.sort_values("_minuto").iloc[-1].to_dict()


def diagnosticar_dna_pressao(atual, anterior, lado, minuto, gols_casa, gols_fora):
    if anterior is None:
        return "EM_FORMAÇÃO", 0.0, "Aguardando o segundo snapshot", 0.0, "INDEFINIDA"

    minuto_anterior = int(numero_af(anterior.get("minuto"), -1))
    intervalo = int(minuto) - minuto_anterior
    if intervalo < 2 or intervalo > 15:
        return (
            "EM_FORMAÇÃO", 0.0,
            f"Janela inválida: {intervalo} minutos entre snapshots",
            0.0, "INDEFINIDA",
        )

    sufixo = "casa" if lado == "casa" else "fora"

    def delta(campo):
        return max(
            0.0,
            numero_af(atual.get(f"{campo}_{sufixo}"))
            - numero_af(anterior.get(f"{campo}_{sufixo}")),
        )

    novos_corners = delta("corners")
    novos_sog = delta("chutes_gol")
    novos_chutes = delta("chutes_total")
    acoes = novos_corners * 3 + novos_sog * 4 + novos_chutes

    gols_time = gols_casa if lado == "casa" else gols_fora
    gols_rival = gols_fora if lado == "casa" else gols_casa
    if gols_time < gols_rival:
        situacao = "PERDENDO"
    elif gols_time > gols_rival:
        situacao = "VENCENDO"
    else:
        situacao = "EMPATANDO"

    motivos = []
    if novos_sog >= 2:
        motivos.append(f"{int(novos_sog)} novos chutes no gol")
    elif novos_sog >= 1:
        motivos.append("novo chute no gol")
    if novos_corners >= 2:
        motivos.append(f"{int(novos_corners)} novos escanteios")
    elif novos_corners >= 1:
        motivos.append("novo escanteio")
    if novos_chutes >= 4:
        motivos.append(f"{int(novos_chutes)} novas finalizações")

    score = min(
        100.0,
        novos_sog * 25 + novos_corners * 15 + novos_chutes * 5,
    )
    if minuto >= 70 and situacao == "PERDENDO" and acoes >= 8:
        tipo = "DESESPERADA"
        motivos.append("time perdendo após os 70 minutos")
    elif novos_sog >= 1 and (novos_corners >= 1 or novos_chutes >= 3):
        tipo = "PERIGOSA"
    elif acoes >= 5 and novos_sog == 0:
        tipo = "ESTÉRIL"
        motivos.append("pressão sem chute no gol")
        score = min(score, 45.0)
    else:
        tipo = "EM_CONSTRUÇÃO"
        motivos.append("volume ofensivo ainda limitado")

    return tipo, round(score, 1), "; ".join(motivos), round(acoes, 1), situacao


def atualizar_validacao_af(linha):
    df = ler_csv_github_generico(
        APIFOOTBALL_VALIDACAO_PATH, COLUNAS_VALIDACAO_APIFOOTBALL
    )
    if df.empty:
        return
    mascara = (
        df["fixture_id"].astype(str).eq(str(linha["fixture_id"]))
        & df["status"].astype(str).eq("ACOMPANHANDO")
    )
    mudou = False
    gols_atuais = sum(int(numero_af(x)) for x in str(linha["placar"]).split(" x "))
    corners_atuais = numero_af(linha["corners_casa"]) + numero_af(linha["corners_fora"])
    for idx in df.index[mascara]:
        minuto_alerta = int(numero_af(df.at[idx, "minuto_alerta"]))
        delta_min = int(numero_af(linha["minuto"])) - minuto_alerta
        gols_alerta = sum(int(numero_af(x)) for x in str(df.at[idx, "placar_alerta"]).split(" x "))
        corners_alerta = numero_af(df.at[idx, "corners_alerta"])
        houve_gol = gols_atuais > gols_alerta
        houve_corner = corners_atuais > corners_alerta
        if 5 <= delta_min <= 10:
            df.at[idx, "gol_ate_5_min"] = "SIM" if houve_gol else "NÃO"
            df.at[idx, "escanteio_ate_5_min"] = "SIM" if houve_corner else "NÃO"
            mudou = True
        if delta_min >= 10:
            df.at[idx, "gol_ate_10_min"] = "SIM" if houve_gol else "NÃO"
            df.at[idx, "escanteio_ate_10_min"] = "SIM" if houve_corner else "NÃO"
            df.at[idx, "status"] = "CONCLUÍDO"
            mudou = True
    if mudou:
        salvar_csv_github_generico(
            APIFOOTBALL_VALIDACAO_PATH, df,
            "Atualiza validação API-Football"
        )


def registrar_alerta_af(linha):
    df = ler_csv_github_generico(
        APIFOOTBALL_VALIDACAO_PATH, COLUNAS_VALIDACAO_APIFOOTBALL
    )
    fixture_id = linha["fixture_id"]
    if not df.empty and (
        df["fixture_id"].astype(str).eq(str(fixture_id))
        & df["status"].astype(str).eq("ACOMPANHANDO")
    ).any():
        return False
    agora = datetime.now()
    registro = {coluna: "" for coluna in COLUNAS_VALIDACAO_APIFOOTBALL}
    registro.update({
        "id_alerta": f"AF-{fixture_id}-{agora.strftime('%Y%m%d%H%M%S')}",
        "data_hora_alerta": agora.strftime("%Y-%m-%d %H:%M:%S"),
        "fixture_id": fixture_id,
        "jogo": linha["jogo"],
        "minuto_alerta": linha["minuto"],
        "placar_alerta": linha["placar"],
        "time_destaque": linha["time_destaque"],
        "indice_alerta": linha["indice_destaque"],
        "momento_10_min": max(linha["momento_casa"], linha["momento_fora"]),
        "corners_alerta": numero_af(linha["corners_casa"]) + numero_af(linha["corners_fora"]),
        "dna_pressao": linha["dna_pressao"],
        "dna_score": linha["dna_score"],
        "dna_motivos": linha["dna_motivos"],
        "situacao_placar": linha["situacao_placar"],
        "gol_ate_5_min": "PENDENTE", "gol_ate_10_min": "PENDENTE",
        "escanteio_ate_5_min": "PENDENTE", "escanteio_ate_10_min": "PENDENTE",
        "status": "ACOMPANHANDO",
    })
    df = pd.concat([df, pd.DataFrame([registro])], ignore_index=True)
    if not salvar_csv_github_generico(
        APIFOOTBALL_VALIDACAO_PATH, df, "Registra alerta API-Football"
    ):
        return False
    enviar_alerta_telegram(
        "🚨 PRESSÃO ALTA — API-FOOTBALL\n\n"
        f"⚽ {linha['jogo']}\n"
        f"⏱ Minuto: {int(numero_af(linha['minuto']))}'\n"
        f"📍 Placar: {linha['placar']}\n"
        f"🔥 Destaque: {linha['time_destaque']}\n"
        f"📊 Índice: {numero_af(linha['indice_destaque']):.1f}%\n"
        f"⚡ Momento recente: {max(linha['momento_casa'], linha['momento_fora']):.1f}%\n\n"
        f"🧬 DNA: {linha['dna_pressao']} ({numero_af(linha['dna_score']):.0f}/100)\n"
        f"🔎 {linha['dna_motivos']}\n"
        f"🎯 Situação: {linha['situacao_placar']}\n\n"
        "🧪 Sinal estatístico em validação; nenhuma aposta é automática."
    )
    return True


def rastreamento_ativo_af(df, fixture_id):
    if df.empty or fixture_id is None:
        return None
    historico = df[df["fixture_id"].astype(str).eq(str(fixture_id))].copy()
    if historico.empty:
        return None
    for coluna in [
        "rastreamento_id", "rastreamento_origem_minuto", "rastreamento_etapa",
    ]:
        if coluna not in historico.columns:
            historico[coluna] = ""
    historico["minuto_ordem"] = pd.to_numeric(
        historico["minuto"], errors="coerce"
    )
    historico["data_ordem"] = pd.to_datetime(
        historico["data_hora"], errors="coerce"
    )
    historico = historico.sort_values(["minuto_ordem", "data_ordem"])
    ultimo = historico.iloc[-1]
    etapa = str(ultimo["rastreamento_etapa"]).strip().upper()
    identificador = str(ultimo["rastreamento_id"]).strip()
    if not identificador or identificador.lower() in {"nan", "none"}:
        return None
    if etapa not in {"AGUARDANDO_5", "AGUARDANDO_10"}:
        return None
    return {
        "id": identificador,
        "origem_minuto": int(numero_af(ultimo["rastreamento_origem_minuto"])),
        "etapa": etapa,
    }


def origem_rastreamento_af(df, rastreamento_id):
    if df.empty or not rastreamento_id:
        return None
    historico = df[
        df["rastreamento_id"].astype(str).eq(str(rastreamento_id))
    ].copy()
    if historico.empty:
        return None
    historico["minuto_ordem"] = pd.to_numeric(
        historico["minuto"], errors="coerce"
    )
    historico["data_ordem"] = pd.to_datetime(
        historico["data_hora"], errors="coerce"
    )
    return historico.sort_values(["minuto_ordem", "data_ordem"]).iloc[0]


def total_gols_af(placar):
    try:
        partes = str(placar).lower().replace("×", "x").replace("-", "x").split("x")
        if len(partes) != 2:
            return None
        return int(numero_af(partes[0])) + int(numero_af(partes[1]))
    except Exception:
        return None


def calcular_curva_pressao_af(origem, linha):
    if origem is None:
        return "INICIADA", 0.0
    indice_origem = numero_af(origem.get("indice_destaque"))
    indice_atual = numero_af(linha.get("indice_destaque"))
    variacao = round(indice_atual - indice_origem, 1)
    gols_origem = total_gols_af(origem.get("placar"))
    gols_atual = total_gols_af(linha.get("placar"))
    if gols_origem is not None and gols_atual is not None and gols_atual > gols_origem:
        return "⚽ GOL APÓS O SINAL", variacao
    if str(origem.get("time_destaque", "")) != str(linha.get("time_destaque", "")):
        return "🔄 PRESSÃO INVERTEU", variacao
    if variacao >= 10:
        return "🚀 ACELERANDO", variacao
    if str(linha.get("nivel_pressao", "")).upper() == "ALTA" and variacao >= -5:
        return "🔥 FORTE SUSTENTADA", variacao
    if -5 < variacao < 5:
        return "⚖️ ESTÁVEL", variacao
    if variacao <= -10:
        return "📉 PERDEU FORÇA", variacao
    return "〰️ OSCILANDO", variacao


def confirmacao_telegram_ja_enviada_af(df, rastreamento_id):
    if df.empty or not rastreamento_id or "confirmacao_telegram_enviada" not in df.columns:
        return False
    mascara = df["rastreamento_id"].astype(str).eq(str(rastreamento_id))
    return df.loc[mascara, "confirmacao_telegram_enviada"].astype(str).str.upper().eq("SIM").any()


def candidato_rastreamento_af(linha):
    nivel = str(linha.get("nivel_pressao", "")).strip().upper()
    minuto = int(numero_af(linha.get("minuto"), -1))
    indice = numero_af(linha.get("indice_destaque"))
    dna_score = numero_af(linha.get("dna_score"))
    dna = str(linha.get("dna_pressao", "")).strip().upper()
    if nivel == "ALTA":
        return True
    return (
        nivel in {"MODERADA", "COLETANDO"}
        and 10 <= minuto <= 80
        and (indice >= 60 or dna_score >= 50 or dna in {"PERIGOSA", "DESESPERADA"})
    )


def ha_rastreamento_pendente_af(df, fixture_ids_ativos):
    return any(
        rastreamento_ativo_af(df, fixture_id) is not None
        for fixture_id in fixture_ids_ativos
    )


def priorizar_jogos_apifootball(jogos, df):
    """Ordena candidatos usando apenas dados já disponíveis, sem nova chamada."""
    candidatos = []
    for jogo in jogos:
        fixture = jogo.get("fixture", {}) or {}
        fixture_id = fixture.get("id")
        minuto = int(numero_af((fixture.get("status", {}) or {}).get("elapsed"), -1))
        liga = str((jogo.get("league", {}) or {}).get("name", "")).strip()
        pontos = 0.0
        motivos = []

        rastreamento = rastreamento_ativo_af(df, fixture_id)
        if rastreamento:
            pontos += 300
            etapa = rastreamento["etapa"].replace("_", " ").lower()
            motivos.append(f"confirmação prioritária {etapa}")

        historico_fixture = pd.DataFrame()
        if not df.empty and fixture_id is not None:
            historico_fixture = df[
                df["fixture_id"].astype(str).eq(str(fixture_id))
            ].copy()
        if not historico_fixture.empty:
            minutos_anteriores = pd.to_numeric(
                historico_fixture["minuto"], errors="coerce"
            ).dropna()
            if not minutos_anteriores.empty:
                delta = minuto - int(minutos_anteriores.max())
                if 2 <= delta <= 15:
                    pontos += 100
                    motivos.append(f"continuidade de janela ({delta} min)")
                elif delta <= 1:
                    pontos -= 15
                    motivos.append("snapshot recente demais")
                elif delta > 15:
                    pontos += 5
                    motivos.append("histórico existente, janela reiniciada")

        if 10 <= minuto <= 75:
            pontos += 25
            motivos.append("minuto útil")
        elif 76 <= minuto <= 85:
            pontos += 10
            motivos.append("reta final")
        elif minuto > 85:
            pontos -= 10
            motivos.append("tempo restante reduzido")

        historico_liga = pd.DataFrame()
        if not df.empty and liga:
            historico_liga = df[df["liga"].astype(str).eq(liga)].copy()
        if historico_liga.empty:
            pontos += 8
            motivos.append("liga em exploração")
        else:
            qualidade = historico_liga["qualidade_coleta"].astype(str).str.upper()
            taxa_alta = qualidade.eq("ALTA").mean()
            bonus_qualidade = taxa_alta * 30
            pontos += bonus_qualidade
            motivos.append(f"dados ALTA históricos {taxa_alta * 100:.0f}%")
            pontos += min(10, len(historico_liga)) * 0.5

        candidatos.append((
            round(pontos, 1),
            "; ".join(motivos) or "sem prioridade específica",
            jogo,
        ))

    candidatos.sort(key=lambda item: item[0], reverse=True)
    return candidatos


def processar_jogo_af(jogo, df, restante, prioridade=0.0, motivo_prioridade=""):
    fixture = jogo.get("fixture", {}) or {}
    fixture_id = fixture.get("id")
    minuto = (fixture.get("status", {}) or {}).get("elapsed")
    if fixture_id is None or minuto is None:
        return df, restante, False
    rastreamento = rastreamento_ativo_af(df, fixture_id)
    stats_resp, restante_stats = apifootball_get(
        "fixtures/statistics", {"fixture": fixture_id}
    )
    if stats_resp is None:
        return df, restante_stats, False
    stats = extrair_stats_apifootball(stats_resp)
    times = jogo.get("teams", {}) or {}
    casa = (times.get("home", {}) or {}).get("name", "Casa")
    fora = (times.get("away", {}) or {}).get("name", "Visitante")
    goals = jogo.get("goals", {}) or {}
    league = jogo.get("league", {}) or {}
    campos = {
        "posse_casa": stat_af(stats, "home", ["Ball Possession"]),
        "posse_fora": stat_af(stats, "away", ["Ball Possession"]),
        "corners_casa": stat_af(stats, "home", ["Corner Kicks"]),
        "corners_fora": stat_af(stats, "away", ["Corner Kicks"]),
        "chutes_gol_casa": stat_af(stats, "home", ["Shots on Goal"]),
        "chutes_gol_fora": stat_af(stats, "away", ["Shots on Goal"]),
        "chutes_total_casa": stat_af(stats, "home", ["Total Shots"]),
        "chutes_total_fora": stat_af(stats, "away", ["Total Shots"]),
        "amarelos_casa": stat_af(stats, "home", ["Yellow Cards"]),
        "amarelos_fora": stat_af(stats, "away", ["Yellow Cards"]),
        "vermelhos_casa": stat_af(stats, "home", ["Red Cards"]),
        "vermelhos_fora": stat_af(stats, "away", ["Red Cards"]),
    }
    essenciais = [campos[x] for x in (
        "posse_casa", "posse_fora", "corners_casa", "corners_fora",
        "chutes_gol_casa", "chutes_gol_fora"
    )]
    cobertura = sum(x is not None for x in essenciais) / len(essenciais) * 100
    qualidade = "ALTA" if cobertura >= 83 else "MEDIA" if cobertura >= 50 else "INSUFICIENTE"
    numericos = {chave: numero_af(valor) for chave, valor in campos.items()}
    indice_h, indice_a = indices_apifootball(numericos)
    base = {**numericos, "minuto": minuto}
    anterior = ultimo_snapshot_af(df, fixture_id, minuto)
    momento_h, momento_a, tem_janela = momento_apifootball(base, anterior)
    combinado_h, combinado_a = combinar_indices(indice_h, indice_a, momento_h, momento_a)
    nivel, dominante = classificar_pressao_live(
        combinado_h, combinado_a, momento_h, momento_a, casa, fora
    )
    if not tem_janela or qualidade == "INSUFICIENTE":
        nivel = "COLETANDO"
    # Um gol é resultado, não evidência de que outro gol virá. Bloqueamos o
    # sinal por três minutos e deixamos a janela ofensiva recomeçar.
    ultimo_gol_af = None
    for evento in jogo.get("events", []) or []:
        tipo_evento = str(evento.get("type", "")).strip().lower()
        if tipo_evento != "goal":
            continue
        try:
            minuto_evento = int((evento.get("time", {}) or {}).get("elapsed"))
            if minuto_evento <= int(minuto):
                ultimo_gol_af = max(ultimo_gol_af or minuto_evento, minuto_evento)
        except (TypeError, ValueError):
            pass
    if ultimo_gol_af is None and anterior is not None:
        try:
            gols_antes = sum(
                int(numero_af(x)) for x in str(anterior.get("placar", "0 x 0")).split(" x ")
            )
            gols_agora = int(numero_af(goals.get("home"))) + int(numero_af(goals.get("away")))
            if gols_agora > gols_antes:
                ultimo_gol_af = int(minuto)
        except Exception:
            pass
    if ultimo_gol_af is not None and 0 <= int(minuto) - ultimo_gol_af <= 3:
        nivel = "PÓS_GOL"
    lado_destaque = "casa" if combinado_h >= combinado_a else "fora"
    dna_tipo, dna_score, dna_motivos, acoes_recentes, situacao_placar = (
        diagnosticar_dna_pressao(
            base,
            anterior,
            lado_destaque,
            int(minuto),
            int(numero_af(goals.get("home"))),
            int(numero_af(goals.get("away"))),
        )
    )
    motivos_bloqueio = []
    if not tem_janela:
        motivos_bloqueio.append("sem janela recente válida")
    if qualidade != "ALTA":
        motivos_bloqueio.append("qualidade dos dados abaixo de ALTA")
    if nivel != "ALTA":
        motivos_bloqueio.append(f"pressão geral {nivel}")
    if dna_tipo != "PERIGOSA":
        motivos_bloqueio.append(f"DNA {dna_tipo}")
    if numero_af(dna_score) < 60:
        motivos_bloqueio.append("DNA score abaixo de 60")
    elegivel_telegram = not motivos_bloqueio
    linha = {
        "data_hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "fixture_id": fixture_id, "liga": league.get("name", ""),
        "pais": league.get("country", ""), "jogo": f"{casa} x {fora}",
        "minuto": int(minuto),
        "placar": f"{goals.get('home', 0)} x {goals.get('away', 0)}",
        "status": (fixture.get("status", {}) or {}).get("short", ""),
        **campos, "qualidade_coleta": qualidade,
        "quota_restante": restante_stats if restante_stats >= 0 else restante,
        "indice_casa": combinado_h, "indice_fora": combinado_a,
        "momento_casa": momento_h, "momento_fora": momento_a,
        "nivel_pressao": nivel, "time_destaque": dominante,
        "indice_destaque": max(combinado_h, combinado_a),
        "diferenca": round(abs(combinado_h - combinado_a), 1),
        "dna_pressao": dna_tipo,
        "dna_score": dna_score,
        "dna_motivos": dna_motivos,
        "acoes_recentes_destaque": acoes_recentes,
        "situacao_placar": situacao_placar,
        "elegivel_telegram": "SIM" if elegivel_telegram else "NÃO",
        "motivo_bloqueio": "; ".join(motivos_bloqueio),
        "prioridade_coleta": prioridade,
        "motivo_prioridade": motivo_prioridade,
        "rastreamento_id": "",
        "rastreamento_origem_minuto": "",
        "rastreamento_etapa": "",
        "curva_pressao": "",
        "variacao_indice": "",
        "confirmacao_telegram_enviada": "NÃO",
    }
    origem_rastreamento = None
    delta_confirmacao = 0
    if rastreamento:
        origem_minuto = rastreamento["origem_minuto"]
        delta_confirmacao = int(minuto) - origem_minuto
        linha["rastreamento_id"] = rastreamento["id"]
        linha["rastreamento_origem_minuto"] = origem_minuto
        origem_rastreamento = origem_rastreamento_af(df, rastreamento["id"])
        if delta_confirmacao >= 10:
            linha["rastreamento_etapa"] = "CONCLUÍDO"
        elif delta_confirmacao >= 5:
            linha["rastreamento_etapa"] = "AGUARDANDO_10"
        else:
            linha["rastreamento_etapa"] = "AGUARDANDO_5"
    elif candidato_rastreamento_af(linha):
        linha["rastreamento_id"] = (
            f"AFQ-{fixture_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        )
        linha["rastreamento_origem_minuto"] = int(minuto)
        linha["rastreamento_etapa"] = "AGUARDANDO_5"
        log(
            f"API-Football confirmação iniciada: {linha['jogo']} "
            f"no minuto {int(minuto)}"
        )
    linha["curva_pressao"], linha["variacao_indice"] = (
        calcular_curva_pressao_af(origem_rastreamento, linha)
    )

    if (
        origem_rastreamento is not None
        and delta_confirmacao >= 5
        and str(origem_rastreamento.get("elegivel_telegram", "")).upper() == "SIM"
        and not confirmacao_telegram_ja_enviada_af(df, linha["rastreamento_id"])
    ):
        mensagem_curva = (
            "📈 ATUALIZAÇÃO DA PRESSÃO — API-FOOTBALL\n\n"
            f"⚽ {linha['jogo']}\n"
            f"⏱ Minuto: {int(minuto)}'\n"
            f"📍 Placar: {linha['placar']}\n"
            f"🔥 Destaque: {linha['time_destaque']}\n"
            f"📊 Curva: {linha['curva_pressao']}\n"
            f"↕️ Variação do índice: {numero_af(linha['variacao_indice']):+.1f}\n\n"
            "🧪 Confirmação estatística; nenhuma aposta é automática."
        )
        if enviar_alerta_telegram(mensagem_curva):
            linha["confirmacao_telegram_enviada"] = "SIM"
    elegivel_anterior = (
        str(anterior.get("elegivel_telegram", "")).strip().upper() == "SIM"
        if anterior else False
    )
    atualizar_validacao_af(linha)
    mascara = (
        df["fixture_id"].astype(str).eq(str(fixture_id))
        & pd.to_numeric(df["minuto"], errors="coerce").eq(int(minuto))
    ) if not df.empty else pd.Series(dtype=bool)
    if not df.empty and mascara.any():
        idx = df.index[mascara][-1]
        for chave, valor in linha.items():
            df.at[idx, chave] = valor
    else:
        df = pd.concat([df, pd.DataFrame([linha])], ignore_index=True)
    if elegivel_telegram and not elegivel_anterior:
        registrar_alerta_af(linha)
    elif nivel == "ALTA" and not elegivel_telegram:
        log(
            "API-Football: pressão ALTA registrada para estudo, "
            f"mas Telegram bloqueado ({linha['motivo_bloqueio']})"
        )
    log(
        f"API-Football: {linha['jogo']} min {minuto} • "
        f"pressão {nivel} • DNA {dna_tipo} • dados {qualidade} • "
        f"quota {linha['quota_restante']} • "
        f"confirmação {linha['rastreamento_etapa'] or 'inativa'} • "
        f"curva {linha['curva_pressao'] or 'sem leitura'}"
    )
    return df, linha["quota_restante"], True


def ciclo_apifootball():
    if not APIFOOTBALL_KEY:
        return APIFOOTBALL_INTERVALO_SEGUNDOS
    dados, restante = apifootball_get("fixtures", {"live": "all"})
    if dados is None:
        sentinela_registrar(
            "api_football", False, "A consulta de jogos ao vivo não respondeu."
        )
        return APIFOOTBALL_INTERVALO_SEGUNDOS
    sentinela_registrar(
        "api_football", True, "Consulta de jogos ao vivo concluída."
    )
    sentinela_verificar_cota(restante)
    jogos = dados.get("response", []) or []
    if APIFOOTBALL_LIGAS:
        jogos = [
            jogo for jogo in jogos
            if str((jogo.get("league", {}) or {}).get("id")) in APIFOOTBALL_LIGAS
        ]
    if restante >= 0 and restante <= APIFOOTBALL_RESERVA_DIA:
        log(f"API-Football: reserva diária atingida ({restante} restantes)")
        return APIFOOTBALL_INTERVALO_SEGUNDOS
    if not jogos:
        log(f"API-Football: 0 jogos ao vivo • quota restante {restante}")
        return APIFOOTBALL_INTERVALO_SEGUNDOS
    df = ler_csv_github_generico(APIFOOTBALL_PATH, COLUNAS_APIFOOTBALL)
    processados = 0
    candidatos = priorizar_jogos_apifootball(jogos, df)
    selecionados = candidatos[:max(1, APIFOOTBALL_MAX_JOGOS)]
    for prioridade, motivo_prioridade, jogo in selecionados:
        if restante >= 0 and restante <= APIFOOTBALL_RESERVA_DIA:
            break
        try:
            fixture_nome = (
                f"{((jogo.get('teams', {}) or {}).get('home', {}) or {}).get('name', 'Casa')} x "
                f"{((jogo.get('teams', {}) or {}).get('away', {}) or {}).get('name', 'Visitante')}"
            )
            log(
                f"API-Football radar: {fixture_nome} • prioridade {prioridade:.1f} • "
                f"{motivo_prioridade}"
            )
            df, restante, mudou = processar_jogo_af(
                jogo, df, restante, prioridade, motivo_prioridade
            )
            processados += int(mudou)
        except Exception as exc:
            log(f"API-Football erro em fixture: {exc}")
    ok = salvar_csv_github_generico(
        APIFOOTBALL_PATH, df, "Atualiza pressão API-Football"
    )
    sentinela_registrar(
        "github", ok, "Persistência do monitoramento da API-Football."
    )
    log(
        f"API-Football: {len(jogos)} ao vivo • {processados} processados • "
        f"GitHub {'OK' if ok else 'FALHOU'}"
    )
    fixture_ids_ativos = {
        (jogo.get("fixture", {}) or {}).get("id") for jogo in jogos
    }
    if ha_rastreamento_pendente_af(df, fixture_ids_ativos):
        log(
            "API-Football: confirmação pendente; próxima leitura em "
            f"{APIFOOTBALL_CONFIRMACAO_SEGUNDOS} segundos"
        )
        return APIFOOTBALL_CONFIRMACAO_SEGUNDOS
    return APIFOOTBALL_INTERVALO_SEGUNDOS


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


def fixture_sportmonks_encerrado(jogo):
    estado = jogo.get("state", {}) or {}
    texto = " ".join(
        str(estado.get(campo, ""))
        for campo in ("name", "short_name", "developer_name", "state")
    ).strip().lower()
    termos = (
        "finished", "full time", "fulltime", "after penalties",
        "after extra time", "ended", "finalizado", "ft", "aet", "pen",
    )
    palavras = set(texto.replace("-", " ").split())
    return any(termo in texto for termo in termos[:-3]) or bool(
        palavras.intersection({"ft", "aet", "pen"})
    )


def idade_alerta_horas(valor):
    try:
        horario = pd.to_datetime(valor, errors="coerce")
        if pd.isna(horario):
            return 0.0
        agora = pd.Timestamp.now(tz="UTC")
        if horario.tzinfo is None:
            horario = horario.tz_localize("UTC")
        else:
            horario = horario.tz_convert("UTC")
        return max(0.0, (agora - horario).total_seconds() / 3600)
    except Exception:
        return 0.0


def encerrar_campos_corner_sem_dados(df, idx):
    for coluna in (
        "escanteio_ate_5_min", "escanteio_ate_10_min",
        "escanteio_time_destaque_5_min", "escanteio_time_destaque_10_min",
    ):
        if coluna in df.columns and str(df.at[idx, coluna]).strip() == "PENDENTE":
            df.at[idx, coluna] = "NÃO AVALIADO"


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
                if idade_alerta_horas(df.at[idx, "data_hora_alerta"]) >= 6:
                    df.at[idx, "status"] = "DADOS_INDISPONIVEIS"
                    df.at[idx, "resultado_gol"] = "NÃO AVALIADO"
                    for coluna in (
                        "gol_ate_5_min", "gol_ate_10_min",
                        "gol_time_destaque_5_min", "gol_time_destaque_10_min",
                    ):
                        df.at[idx, coluna] = "NÃO AVALIADO"
                    encerrar_campos_corner_sem_dados(df, idx)
                    alterou = True
                continue

            casa, visitante, ids, nomes = identificar_times(jogo)

            eventos = preparar_eventos(
                jogo,
                nomes
            )

            minuto_atual = minuto_estimado(jogo)
            encerrado = fixture_sportmonks_encerrado(jogo)
            if encerrado:
                minuto_atual = max(90, minuto_atual or 0)

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
                encerrar_campos_corner_sem_dados(df, idx)

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
                encerrar_campos_corner_sem_dados(df, idx)

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
        return 0
    if "red" in nome:
        return -6
    if "yellow" in nome:
        return -2
    if "substitution" in nome:
        return 0
    if "corner" in nome or "escanteio" in nome:
        return 3
    if "shot on target" in nome or "shot on goal" in nome:
        return 4
    if "shot" in nome or "finaliza" in nome:
        return 2
    if "dangerous attack" in nome or "ataque perigoso" in nome:
        return 2
    if "attack" in nome or "ataque" in nome:
        return 1
    return 0

def pressao_eventos(eventos, minuto_atual, casa, visitante, janela=10):
    inicio = max(0, minuto_atual - janela)
    gols_anteriores = [
        e for e in eventos
        if "goal" in str(e.get("Evento", "")).lower()
        and e["minuto_num"] <= minuto_atual
    ]
    if gols_anteriores:
        inicio = max(inicio, max(e["minuto_num"] for e in gols_anteriores))
    recentes = [
        e for e in eventos
        if inicio < e["minuto_num"] <= minuto_atual
        and "goal" not in str(e.get("Evento", "")).lower()
    ]
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
        df = pd.read_csv(
            StringIO(texto),
            dtype=object
        )
    except Exception as exc:
        log(f"Erro ao ler GitHub: {exc}")
        return pd.DataFrame(columns=COLUNAS_MONITORAMENTO)

    for c in COLUNAS_MONITORAMENTO:
        if c not in df.columns:
            df[c] = ""
    return df[COLUNAS_MONITORAMENTO].astype("object")

def ler_validacoes_github():
    return ler_csv_github_generico(
        ARQUIVO_VALIDACAO,
        COLUNAS_VALIDACAO
    )


def atualizar_resultados_financeiros(df):
    if df.empty:
        return df

    for idx in df.index:
        try:
            odd = float(df.at[idx, "odd_simulada"])
            stake = float(df.at[idx, "stake_simulada"])
        except (TypeError, ValueError):
            continue

        if odd <= 1 or stake <= 0:
            continue

        desfecho = str(df.at[idx, "gol_ate_10_min"]).strip().upper()

        if desfecho == "SIM":
            df.at[idx, "resultado_financeiro"] = "GREEN"
            df.at[idx, "lucro_prejuizo"] = round(
                stake * (odd - 1), 2
            )
        elif desfecho in {"NÃO", "NAO"}:
            df.at[idx, "resultado_financeiro"] = "RED"
            df.at[idx, "lucro_prejuizo"] = round(-stake, 2)
        else:
            df.at[idx, "resultado_financeiro"] = "ACOMPANHANDO"
            df.at[idx, "lucro_prejuizo"] = ""

    return df


def salvar_validacoes_github(df):
    df = atualizar_resultados_financeiros(df)
    return salvar_csv_github_generico(
        ARQUIVO_VALIDACAO,
        df,
        "Atualiza validação automática"
    )


def calcular_qualidade_alerta_worker(
    indice,
    momento,
    posse,
    vantagem_escanteios,
):
    pontos_indice = max(0, min(40, (float(indice) - 50) * 2))
    pontos_momento = max(0, min(35, (float(momento) - 50) * 1.75))
    pontos_posse = max(0, min(15, (float(posse) - 50)))
    pontos_corners = max(0, min(10, float(vantagem_escanteios) * 2.5))
    score = round(
        max(0, min(100, pontos_indice + pontos_momento + pontos_posse + pontos_corners)),
        1,
    )

    if score >= 80:
        nivel = "EXCEPCIONAL"
    elif score >= 65:
        nivel = "MUITO FORTE"
    elif score >= 50:
        nivel = "FORTE"
    elif score >= 35:
        nivel = "MODERADO"
    else:
        nivel = "FRACO"

    return score, nivel


def registrar_alerta_alta_worker(
    fixture_id,
    casa,
    visitante,
    minuto,
    gols_casa,
    gols_visitante,
    dominante,
    indice,
    momento,
    posse,
    vantagem_escanteios,
):
    df = ler_validacoes_github()

    if not df.empty:
        fixture_igual = df["fixture_id"].astype(str).eq(str(fixture_id))
        minuto_igual = pd.to_numeric(
            df["minuto_alerta"], errors="coerce"
        ).eq(int(minuto))
        if (fixture_igual & minuto_igual).any():
            return False

    agora = datetime.now()
    score, qualidade_nivel = calcular_qualidade_alerta_worker(
        indice,
        momento,
        posse,
        vantagem_escanteios,
    )
    linha = {coluna: "" for coluna in COLUNAS_VALIDACAO}
    linha.update({
        "id_alerta": f"{fixture_id}-{agora.strftime('%Y%m%d%H%M%S')}",
        "data_hora_alerta": agora.strftime("%Y-%m-%d %H:%M:%S"),
        "fixture_id": fixture_id,
        "jogo": f"{casa} x {visitante}",
        "minuto_alerta": int(minuto),
        "placar_alerta": f"{gols_casa} x {gols_visitante}",
        "time_destaque": dominante,
        "indice_alerta": round(float(indice), 1),
        "momento_10_min": round(float(momento), 1),
        "qualidade_score": score,
        "qualidade_nivel": qualidade_nivel,
        "gol_ate_5_min": "PENDENTE",
        "gol_ate_10_min": "PENDENTE",
        "resultado_gol": "PENDENTE",
        "gol_time_destaque_5_min": "PENDENTE",
        "gol_time_destaque_10_min": "PENDENTE",
        "escanteio_ate_5_min": "PENDENTE",
        "escanteio_ate_10_min": "PENDENTE",
        "escanteio_time_destaque_5_min": "PENDENTE",
        "escanteio_time_destaque_10_min": "PENDENTE",
        "resultado_financeiro": "NÃO REGISTRADA",
        "status": "ACOMPANHANDO",
    })

    df = pd.concat([df, pd.DataFrame([linha])], ignore_index=True)
    if not salvar_validacoes_github(df):
        log("Falha ao registrar validação do alerta ALTA")
        return False

    mensagem = (
        "🚨 PRESSÃO ALTA\n\n"
        f"⚽ {casa} x {visitante}\n"
        f"⏱ Minuto: {int(minuto)}'\n"
        f"📍 Placar: {gols_casa} x {gols_visitante}\n"
        f"🔥 Destaque: {dominante}\n"
        f"📊 Índice: {float(indice):.1f}%\n"
        f"⚡ Momento 10 min: {float(momento):.1f}%\n\n"
        "🧪 Simulação: verificar a odd para gol nos próximos 10 minutos.\n"
        "💵 Stake sugerida para o teste: R$ 1,00."
    )
    enviar_alerta_telegram(mensagem)
    return True

def salvar_monitoramento_github(df):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_MONITORAMENTO_PATH}"
    sha = None
    conteudo_novo = df.to_csv(index=False).encode("utf-8")
    try:
        atual = requests.get(url, headers=gh_headers(), params={"ref": GITHUB_BRANCH}, timeout=20)
        if atual.status_code == 200:
            dados_atuais = atual.json()
            sha = dados_atuais.get("sha")
            conteudo_atual = base64.b64decode(
                dados_atuais.get("content", "")
            )
            if conteudo_atual == conteudo_novo:
                log(
                    f"Sem alterações em {GITHUB_MONITORAMENTO_PATH}; "
                    "commit ignorado"
                )
                return True

        payload = {
            "message": "Atualiza monitoramento autÃ´nomo",
            "content": base64.b64encode(conteudo_novo).decode("ascii"),
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

    minutos_gols = [
        int(e.get("minuto_num", 0) or 0)
        for e in eventos
        if "goal" in str(e.get("Evento", "")).lower()
        and int(e.get("minuto_num", 0) or 0) <= int(minuto)
    ]
    if minutos_gols and 0 <= int(minuto) - max(minutos_gols) <= 3:
        nivel = "PÓS_GOL"

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

    nivel_anterior = ""
    if not df.empty:
        anteriores = df[
            df["fixture_id"].astype(str).eq(str(fixture_id))
        ].copy()
        if not anteriores.empty:
            ordem = pd.to_datetime(
                anteriores["data_hora"], errors="coerce"
            )
            if ordem.notna().any():
                nivel_anterior = str(
                    anteriores.loc[ordem.idxmax(), "nivel"]
                ).strip().upper()

    entrou_em_alta = (
        str(nivel).strip().upper() == "ALTA"
        and nivel_anterior != "ALTA"
    )

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

    if entrou_em_alta:
        try:
            registrar_alerta_alta_worker(
                fixture_id=fixture_id,
                casa=casa,
                visitante=visitante,
                minuto=minuto_int,
                gols_casa=gh,
                gols_visitante=ga,
                dominante=dominante,
                indice=indice,
                momento=momento_destaque,
                posse=posse,
                vantagem_escanteios=vantagem_corners,
            )
        except Exception as exc:
            log(f"Erro ao registrar alerta ALTA: {exc}")

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

def linhas_do_dia(df, coluna_data, data_local, fuso):
    if df.empty or coluna_data not in df.columns:
        return df.iloc[0:0].copy()
    horarios = pd.to_datetime(df[coluna_data], errors="coerce", utc=True)
    try:
        datas = horarios.dt.tz_convert(fuso).dt.date
    except Exception:
        datas = horarios.dt.date
    return df[datas.eq(data_local)].copy()


def resumo_resultados_diarios(validacoes):
    if validacoes.empty:
        return 0, 0, 0
    total = len(validacoes)
    coluna = "gol_ate_10_min"
    if coluna not in validacoes.columns:
        return total, 0, 0
    resultados = validacoes[coluna].fillna("").astype(str).str.upper()
    gols = resultados.eq("SIM").sum()
    concluidos = resultados.isin(["SIM", "NÃO", "NAO"]).sum()
    return int(total), int(concluidos), int(gols)


def melhor_liga_diaria(df):
    if df.empty or "liga" not in df.columns:
        return "Sem dados suficientes"
    candidatos = []
    for liga, grupo in df.groupby(df["liga"].fillna("").astype(str)):
        liga = str(liga).strip()
        if not liga or liga.lower() in {"nan", "none"}:
            continue
        qualidade = grupo.get(
            "qualidade_coleta", pd.Series(index=grupo.index, dtype=object)
        ).astype(str).str.upper()
        taxa = qualidade.eq("ALTA").mean() * 100
        candidatos.append((taxa, len(grupo), liga))
    if not candidatos:
        return "Sem dados suficientes"
    taxa, quantidade, liga = max(candidatos, key=lambda x: (x[0], x[1]))
    return f"{liga} ({taxa:.0f}% dados ALTA; {quantidade} snapshot(s))"


def relatorio_ja_enviado(data_texto):
    df = ler_csv_github_generico(
        RELATORIO_DIARIO_PATH, ["data_local", "data_hora_envio", "status"]
    )
    if df.empty:
        return False
    return df["data_local"].astype(str).eq(data_texto).any()


def registrar_relatorio_enviado(data_texto, agora_local):
    colunas = ["data_local", "data_hora_envio", "status"]
    df = ler_csv_github_generico(RELATORIO_DIARIO_PATH, colunas)
    linha = {
        "data_local": data_texto,
        "data_hora_envio": agora_local.strftime("%Y-%m-%d %H:%M:%S"),
        "status": "ENVIADO",
    }
    df = pd.concat([df, pd.DataFrame([linha])], ignore_index=True)
    return salvar_csv_github_generico(
        RELATORIO_DIARIO_PATH, df, "Registra envio do relatório diário"
    )


def montar_relatorio_diario(agora_local):
    fuso = ZoneInfo(RELATORIO_DIARIO_FUSO)
    data_local = agora_local.date()
    monitor = ler_csv_github_generico(APIFOOTBALL_PATH, COLUNAS_APIFOOTBALL)
    monitor_dia = linhas_do_dia(monitor, "data_hora", data_local, fuso)
    validacoes_sm = linhas_do_dia(
        ler_validacoes_github(), "data_hora_alerta", data_local, fuso
    )
    validacoes_af = linhas_do_dia(
        ler_csv_github_generico(
            APIFOOTBALL_VALIDACAO_PATH, COLUNAS_VALIDACAO_APIFOOTBALL
        ),
        "data_hora_alerta", data_local, fuso,
    )

    jogos = (
        monitor_dia["fixture_id"].astype(str).nunique()
        if not monitor_dia.empty else 0
    )
    snapshots = len(monitor_dia)
    altas = (
        monitor_dia["nivel_pressao"].astype(str).eq("ALTA").sum()
        if not monitor_dia.empty else 0
    )
    elegiveis = (
        monitor_dia["elegivel_telegram"].astype(str).eq("SIM").sum()
        if not monitor_dia.empty else 0
    )
    bloqueados = (
        (
            monitor_dia["nivel_pressao"].astype(str).eq("ALTA")
            & ~monitor_dia["elegivel_telegram"].astype(str).eq("SIM")
        ).sum()
        if not monitor_dia.empty else 0
    )
    quota = "não informada"
    if not monitor_dia.empty:
        quotas = pd.to_numeric(monitor_dia["quota_restante"], errors="coerce").dropna()
        if not quotas.empty:
            quota = str(int(quotas.iloc[-1]))

    todas_validacoes = pd.concat(
        [validacoes_sm, validacoes_af], ignore_index=True, sort=False
    )
    total_alertas, concluidos, gols = resumo_resultados_diarios(todas_validacoes)
    taxa = f"{gols / concluidos * 100:.1f}%" if concluidos else "aguardando amostra"
    melhor_liga = melhor_liga_diaria(monitor_dia)

    return (
        "📊 RESUMO DIÁRIO — SMART SPORT\n\n"
        f"📅 {agora_local.strftime('%d/%m/%Y')}\n"
        f"⚽ Jogos observados pela API-Football: {jogos}\n"
        f"📸 Snapshots: {snapshots}\n"
        f"🔥 Pressões ALTA para estudo: {int(altas)}\n"
        f"✅ Elegíveis Telegram: {int(elegiveis)}\n"
        f"🛡 Bloqueados pelo Escudo: {int(bloqueados)}\n"
        f"🚨 Alertas registrados (duas fontes): {total_alertas}\n"
        f"🎯 Validações concluídas: {concluidos}\n"
        f"🥅 Gol em até 10 min: {gols}/{concluidos} ({taxa})\n"
        f"🏆 Melhor cobertura do dia: {melhor_liga}\n"
        f"🔋 Cota API-Football: {quota}\n\n"
        "🤖 Worker funcionando normalmente.\n"
        "🧪 Resultados experimentais; nenhuma aposta é automática."
    )


def talvez_enviar_relatorio_diario():
    if not RELATORIO_DIARIO_ATIVO:
        return False
    try:
        fuso = ZoneInfo(RELATORIO_DIARIO_FUSO)
    except Exception:
        fuso = timezone.utc
    agora_local = datetime.now(timezone.utc).astimezone(fuso)
    horario_alvo = (RELATORIO_DIARIO_HORA, RELATORIO_DIARIO_MINUTO)
    if (agora_local.hour, agora_local.minute) < horario_alvo:
        return False
    data_texto = agora_local.date().isoformat()
    if relatorio_ja_enviado(data_texto):
        return False
    mensagem = montar_relatorio_diario(agora_local)
    if not enviar_alerta_telegram(mensagem):
        return False
    registrar_relatorio_enviado(data_texto, agora_local)
    log(f"Relatório diário enviado ({RELATORIO_DIARIO_FUSO})")
    return True


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
        return False

    if not jogos:
        jogos_fd, status_fd = buscar_jogos_football_data()

        if status_fd == 200:
            log(
                f"football-data.org fallback: "
                f"{len(jogos_fd)} jogos encontrados"
            )

            salvar_agenda_football_data(jogos_fd)

            for partida in jogos_fd[:5]:
                casa = partida.get("homeTeam", {}).get("name", "?")
                fora = partida.get("awayTeam", {}).get("name", "?")
                data = partida.get("utcDate", "?")
                estado = partida.get("status", "?")

                log(
                    f"football-data.org: {casa} x {fora} "
                    f"• {data} • {estado}"
                )
        else:
            log(
                f"football-data.org fallback status {status_fd}"
            )

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
    return True

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
            sportmonks_ok = ciclo()
            sentinela_registrar(
                "sportmonks",
                sportmonks_ok is not False,
                "Consulta da fonte SportMonks.",
            )
        except Exception as exc:
            log(
                f"Erro geral SportMonks: {exc}"
            )
            sentinela_registrar(
                "sportmonks", False, f"Erro geral: {exc}"
            )

        agora = time.time()

        if (
            APIFOOTBALL_KEY
            and agora >= proxima_api_football
        ):
            intervalo_api_football = APIFOOTBALL_INTERVALO_SEGUNDOS
            try:
                intervalo_api_football = ciclo_apifootball()
            except Exception as exc:
                log(
                    f"Erro geral API-Football: {exc}"
                )
                sentinela_registrar(
                    "api_football", False, f"Erro geral: {exc}"
                )

            proxima_api_football = (
                time.time()
                + max(60, int(intervalo_api_football or APIFOOTBALL_INTERVALO_SEGUNDOS))
            )

        try:
            talvez_enviar_relatorio_diario()
        except Exception as exc:
            log(f"Erro no relatório diário: {exc}")

        sentinela_verificar_inatividade()

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
