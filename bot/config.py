import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def get_env(name: str, default: str | None = None) -> str:
    val = os.getenv(name, default)
    if val is None:
        raise RuntimeError(f"Variável de ambiente ausente: {name}")
    val = val.strip()
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        val = val[1:-1]
    return val


@dataclass(frozen=True)
class Config:
    url: str
    usuario: str
    senha: str
    headless: bool

    default_timeout_ms: int = 60000

    # No-Show
    tipo_noshow: str = "11 - CANCELAMENTO AUTOMÁTICO DEVIDO NÃO COMPARECIMENTO NA JANELA PREVISTA"
    motivo_cancelamento: str = "Não chegou a tempo."
    grid_timeout_s: int = 35
    grid_poll_ms: int = 450
    zero_rounds_to_finish: int = 2
    max_cancel_per_unit: int = 1500
    visible_scan_limit: int = 30
    cancel_try_scrolls: int = 4

    # Unidades
    unidades: tuple[str, ...] = (
        "1.1.1 - INPASA SINOP/MT",
        "1.1.2 - INPASA DOURADOS/MS",
        "1.1.3 - INPASA NOVA MUTUM/MT",
        "1.1.6 - INPASA SIDROLANDIA/MS",
        "1.1.8 - INPASA BALSAS/MA",
        "1.1.10 - INPASA LUIS EDUARDO MAGALHAES/BA",
    )


def load_config() -> Config:
    return Config(
        url="https://aplicativo.inpasa.com.br/ords/apex/r/csdesenv/gestao-parceiro/login",
        usuario=os.environ["APLICATIVO__INPASA_USUARIO"],
        senha=os.environ["APLICATIVO__INPASA_SENHA"],

        headless=get_env("HEADLESS", "false").lower() == "true",
        tipo_noshow=get_env(
            "TIPO_NOSHOW",
            "11 - CANCELAMENTO AUTOMÁTICO DEVIDO NÃO COMPARECIMENTO NA JANELA PREVISTA",
        ),
        motivo_cancelamento=get_env("MOTIVO_CANCELAMENTO", "Não chegou a tempo."),
        grid_timeout_s=int(get_env("GRID_TIMEOUT_S", "35")),
        grid_poll_ms=int(get_env("GRID_POLL_MS", "450")),
        zero_rounds_to_finish=int(get_env("ZERO_ROUNDS_TO_FINISH", "2")),
        max_cancel_per_unit=int(get_env("MAX_CANCEL_PER_UNIT", "1500")),
        visible_scan_limit=int(get_env("VISIBLE_SCAN_LIMIT", "30")),
        cancel_try_scrolls=int(get_env("CANCEL_TRY_SCROLLS", "4")),
        default_timeout_ms=int(get_env("DEFAULT_TIMEOUT_MS", "60000")),
    )