from __future__ import annotations

import re
import time
from datetime import datetime

from .base import Stage, StageResult
from ..ui.apex import (
    safe_networkidle,
    fechar_alert_sucesso,
    clicar_sim_confirmacao_apex,
    tentar_confirmacoes_genericas,
)
from ..ui.nav import selecionar_unidade, goto_noshow
from ..report.realtime import anexar_cancelamento_e_persistir


# ============================================================
# EXTRAÇÃO td:nth-child (colunas do Grid)
# ============================================================
COL_MAP = {
    "ID": 3,
    "Tipo Frete": 5,
    "Agendado": 7,
    "Cliente": 8,
    "Periodo": 9,
    "Codigo": 10,  # <- coluna do filtro
    "Descricao": 11,
    "Cpf": 12,
    "Nome": 13,
    "Placas": 14,
}

# ✅ Só pode cancelar se Codigo for um desses
CODIGOS_PERMITIDOS = {"41", "154", "159"}


def _cell_text(row, nth: int) -> str:
    td = row.locator(f"td:nth-child({nth})")
    if td.count() == 0:
        return ""

    # ✅ NUNCA use inner_text() aqui (pode travar em grid virtualizado)
    try:
        txt = td.first.text_content(timeout=800)  # timeout curto para não travar
        return (txt or "").strip()
    except Exception:
        try:
            return (td.first.evaluate("el => (el.textContent || '').trim()") or "").strip()
        except Exception:
            return ""


def extrair_dados_linha_por_colunas(row) -> dict:
    return {nome: _cell_text(row, nth) for nome, nth in COL_MAP.items()}


def normalizar_codigo(valor: str) -> str:
    """
    Mantém só dígitos e remove zeros à esquerda.
    Ex: "041" -> "41", "159 " -> "159"
    """
    if not valor:
        return ""
    digits = re.sub(r"\D+", "", valor)
    return digits.lstrip("0") or digits


def codigo_da_linha(row) -> str:
    return _cell_text(row, COL_MAP["Codigo"])


# ============================================================
# GRID / APEX helpers (ROBUSTO)
# ============================================================
def unidade_codigo(unidade_label: str) -> str:
    m = re.match(r"\s*([0-9]+(?:\.[0-9]+)+)\s*-", unidade_label)
    return m.group(1) if m else unidade_label.strip()


def _aguardar_apex_idle_basico(page):
    """
    Espera overlays/processing comuns do APEX sumirem.
    """
    for sel in ["#apex_wait_overlay", ".u-Processing", ".a-Processing"]:
        try:
            loc = page.locator(sel)
            if loc.count() > 0:
                loc.first.wait_for(state="hidden", timeout=8000)
        except Exception:
            pass


def safe_networkidle_best_effort(page, timeout_ms: int = 8000):
    """
    ✅ Evita travar em networkidle (APEX pode ter long-polling).
    """
    try:
        safe_networkidle(page)
    except Exception:
        pass

    _aguardar_apex_idle_basico(page)
    page.wait_for_timeout(250)


def _grid_root(page):
    """
    Pega o APEX Grid VISÍVEL (APEX pode manter grids ocultos no DOM).
    """
    grids = page.locator("div.a-GV")
    n = grids.count()
    if n == 0:
        return None

    for i in range(n):
        g = grids.nth(i)
        try:
            if not g.is_visible():
                continue
        except Exception:
            continue

        try:
            if g.locator("tbody").count() == 0:
                continue
        except Exception:
            continue

        return g

    return grids.first


def debug_grid_snapshot(page) -> dict:
    root = _grid_root(page)
    if root is None:
        return {"grid": 0, "rows": 0, "bans": 0, "nenhum": 0}

    rows = root.locator("tbody tr[role='row']").count()
    bans = root.locator("span.fa-ban[onclick*=\"P780_ID_CARRAGENDA\"]").count()
    nenhum = root.locator('div.a-GV-altMessage-icon[aria-label="Nenhum dado encontrado"]').count()

    return {"grid": 1, "rows": rows, "bans": bans, "nenhum": nenhum}


def existe_nenhum_dado(page) -> bool:
    root = _grid_root(page)
    if root is None:
        return False

    icon = root.locator('div.a-GV-altMessage-icon[aria-label="Nenhum dado encontrado"]').first
    if icon.count() == 0:
        return False

    try:
        return icon.is_visible()
    except Exception:
        return False


def tem_linhas_no_grid(page) -> bool:
    root = _grid_root(page)
    if root is None:
        return False
    return root.locator("tbody tr[role='row']").count() > 0


def scroll_grid(page):
    root = _grid_root(page)

    candidates = []
    if root is not None:
        candidates.extend(
            [
                root.locator(".a-GV-w-scroll"),
                root.locator(".a-GV-body"),
                root.locator(".a-IRR-tableContainer"),
            ]
        )

    fallback_selectors = [
        ".a-GV-w-scroll",
        ".a-GV-body",
        ".a-IRR-tableContainer",
    ]

    for loc in candidates:
        try:
            if loc.count() > 0:
                el = loc.first
                el.evaluate("el => el.scrollBy(0, Math.floor(el.clientHeight * 0.85))")
                page.wait_for_timeout(450)
                return
        except Exception:
            pass

    for sel in fallback_selectors:
        try:
            loc = page.locator(sel)
            if loc.count() > 0:
                el = loc.first
                el.evaluate("el => el.scrollBy(0, Math.floor(el.clientHeight * 0.85))")
                page.wait_for_timeout(450)
                return
        except Exception:
            pass

    page.keyboard.press("PageDown")
    page.wait_for_timeout(450)


# ============================================================
# ✅ Acha o PRIMEIRO cancelar cuja linha tenha Código permitido
# ============================================================
def achar_cancelar_permitido(page, scan_rows: int = 40):
    """
    Retorna (span_cancelar, row, codigo_normalizado) do primeiro item permitido na tela.
    Se não existir, retorna (None, None, None).

    ✅ Anti-travamento: tolera refresh/virtualização do APEX grid.
    """
    root = _grid_root(page)
    if root is None:
        return None, None, None

    rows = root.locator("tbody tr[role='row']")
    try:
        count = rows.count()
    except Exception:
        return None, None, None

    if count == 0:
        return None, None, None

    limit = min(count, scan_rows)

    for i in range(limit):
        try:
            row = rows.nth(i)

            cod_raw = codigo_da_linha(row)
            cod = normalizar_codigo(cod_raw)

            if cod not in CODIGOS_PERMITIDOS:
                continue

            span = row.locator("span.fa-ban[onclick*=\"apex.item('P780_ID_CARRAGENDA')\"]").first
            if span.count() == 0:
                continue

            return span, row, cod
        except Exception:
            continue

    return None, None, None


def tem_cancelar_permitido_visivel(page, visible_scan_limit: int) -> bool:
    span, _, _ = achar_cancelar_permitido(page, scan_rows=max(10, visible_scan_limit))
    return span is not None


def esperar_grid_responder(page, grid_timeout_s: int, poll_ms: int, visible_scan_limit: int) -> str:
    """
    Retorna:
      - NENHUM_DADO
      - TEM_CANCELAR   (agora significa: TEM CANCELAR PERMITIDO visível)
      - TEM_LINHAS
      - TIMEOUT
    """
    deadline = time.time() + grid_timeout_s

    fechar_alert_sucesso(page)
    safe_networkidle_best_effort(page)
    page.wait_for_timeout(250)

    try:
        page.wait_for_selector("div.a-GV", timeout=min(20000, int(grid_timeout_s * 1000)))
    except Exception:
        return "TIMEOUT"

    while time.time() < deadline:
        fechar_alert_sucesso(page)
        _aguardar_apex_idle_basico(page)

        if tem_cancelar_permitido_visivel(page, visible_scan_limit):
            return "TEM_CANCELAR"

        if tem_linhas_no_grid(page):
            return "TEM_LINHAS"

        if existe_nenhum_dado(page):
            return "NENHUM_DADO"

        page.wait_for_timeout(poll_ms)

    return "TIMEOUT"


# ============================================================
# MODAL: Tipo No-Show (LOV) + Motivo + Salvar + Sim
# ============================================================
def selecionar_tipo_noshow_popup_lov(page, texto_tipo: str):
    fechar_alert_sucesso(page)

    btn = page.locator("#P780_TIPO_NOSHOW_CARREG_lov_btn")
    btn.wait_for(state="visible", timeout=20000)
    btn.click()

    dialog = page.locator("[role='dialog']").last
    dialog.wait_for(state="visible", timeout=20000)

    search_box = None
    for sel in ["input[type='search']", "input[type='text']", "input.apex-item-text"]:
        loc = dialog.locator(sel)
        if loc.count() > 0:
            try:
                loc.first.wait_for(state="visible", timeout=1200)
                search_box = loc.first
                break
            except Exception:
                pass

    if search_box is not None:
        try:
            search_box.click()
            search_box.fill("")
            search_box.type(texto_tipo, delay=15)
            page.keyboard.press("Enter")
            page.wait_for_timeout(800)
        except Exception:
            pass

    candidates = [
        dialog.locator("td", has_text=texto_tipo),
        dialog.locator("a", has_text=texto_tipo),
        dialog.locator("li", has_text=texto_tipo),
        dialog.locator("div", has_text=texto_tipo),
    ]

    for c in candidates:
        if c.count() > 0:
            try:
                c.first.click(timeout=7000)
                break
            except Exception:
                c.first.click(force=True)
                break
    else:
        raise RuntimeError(f"Não consegui selecionar o Tipo No-Show no LOV: {texto_tipo}")

    try:
        dialog.wait_for(state="hidden", timeout=20000)
    except Exception:
        tentar_confirmacoes_genericas(page)


def preencher_tipo_motivo_salvar_e_sim(page, tipo_noshow: str, motivo_texto: str):
    selecionar_tipo_noshow_popup_lov(page, tipo_noshow)

    motivo = page.locator("#P780_MOTIVO_CARREGAMENTO")
    motivo.wait_for(state="visible", timeout=20000)
    motivo.click()
    motivo.fill("")
    motivo.type(motivo_texto, delay=20)

    salvar = page.locator("#B11387677950628226010")
    salvar.wait_for(state="visible", timeout=20000)
    page.wait_for_timeout(450)

    try:
        salvar.click(timeout=7000)
    except Exception:
        page.wait_for_timeout(900)
        salvar.click(force=True)

    page.wait_for_timeout(800)
    if not clicar_sim_confirmacao_apex(page):
        tentar_confirmacoes_genericas(page)

    safe_networkidle_best_effort(page)
    page.wait_for_timeout(500)
    fechar_alert_sucesso(page)


def modal_cancelamento_abriu(page) -> bool:
    loc = page.locator("#P780_TIPO_NOSHOW_CARREG_lov_btn")
    try:
        return loc.count() > 0 and loc.first.is_visible()
    except Exception:
        return loc.count() > 0


def clicar_cancelar_com_retry(page, span_cancelar) -> bool:
    for _ in range(6):
        try:
            span_cancelar.wait_for(state="attached", timeout=2000)
        except Exception:
            page.wait_for_timeout(200)
            continue

        try:
            span_cancelar.scroll_into_view_if_needed(timeout=5000)
        except Exception:
            pass

        try:
            span_cancelar.click(timeout=3000)
        except Exception:
            try:
                span_cancelar.click(force=True, timeout=3000)
            except Exception:
                try:
                    span_cancelar.evaluate("el => el.click()")
                except Exception:
                    page.wait_for_timeout(250)
                    continue

        page.wait_for_timeout(600)
        if modal_cancelamento_abriu(page):
            return True

        page.wait_for_timeout(400)

    return False


# ============================================================
# ✅ NOVO: helpers de progresso / recovery
# ============================================================
def _top_row_id(page) -> str | None:
    root = _grid_root(page)
    if root is None:
        return None
    try:
        first_row = root.locator("tbody tr[role='row']").first
        if first_row.count() == 0:
            return None
        return first_row.get_attribute("data-id")
    except Exception:
        return None


def _grid_recovery(page):
    # tenta “destravar” UI do APEX
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
    except Exception:
        pass

    fechar_alert_sucesso(page)
    safe_networkidle_best_effort(page)
    _aguardar_apex_idle_basico(page)

    # volta pro topo e dá um scroll pequeno (força repaint do virtual grid)
    try:
        page.keyboard.press("Home")
        page.wait_for_timeout(250)
    except Exception:
        pass

    try:
        root = _grid_root(page)
        if root is not None:
            body = root.locator(".a-GV-w-scroll").first
            if body.count() > 0:
                body.evaluate("el => el.scrollBy(0, 120)")
                page.wait_for_timeout(250)
    except Exception:
        pass


def _esperar_progresso_apos_cancelar(page, top_id_antes: str | None, timeout_ms: int = 12000) -> bool:
    """
    Retorna True se o grid “andou” (top row mudou ou apareceu 'Nenhum dado'),
    False se não detectou mudança no tempo.
    """
    deadline = time.time() + (timeout_ms / 1000)
    while time.time() < deadline:
        _aguardar_apex_idle_basico(page)
        try:
            if existe_nenhum_dado(page):
                return True
        except Exception:
            pass

        top_id_depois = _top_row_id(page)
        if top_id_antes and top_id_depois and top_id_depois != top_id_antes:
            return True

        page.wait_for_timeout(300)

    return False


# ============================================================
# CANCELAMENTO (ATUALIZADOS)
# ============================================================
def cancelar_um_item_visivel(ctx, unidade_cod: str, cancelados: list[dict]) -> bool:
    page = ctx.page
    cfg = ctx.config

    fechar_alert_sucesso(page)

    # garante que o grid respondeu antes de tentar achar
    esperar_grid_responder(
        page,
        grid_timeout_s=cfg.grid_timeout_s,
        poll_ms=cfg.grid_poll_ms,
        visible_scan_limit=cfg.visible_scan_limit,
    )

    span_cancelar, row0, cod = achar_cancelar_permitido(page, scan_rows=max(20, cfg.visible_scan_limit))
    if span_cancelar is None or row0 is None:
        return False

    top_id_antes = _top_row_id(page)

    dados = {
        "Unidade": unidade_cod,
        "CanceladoEm": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "TipoNoShow": cfg.tipo_noshow,
        "Motivo": cfg.motivo_cancelamento,
    }
    try:
        dados.update(extrair_dados_linha_por_colunas(row0))
    except Exception:
        pass

    fechar_alert_sucesso(page)

    if not clicar_cancelar_com_retry(page, span_cancelar):
        return False

    preencher_tipo_motivo_salvar_e_sim(page, cfg.tipo_noshow, cfg.motivo_cancelamento)

    # ✅ espera o grid realmente “andar”
    ok_progresso = _esperar_progresso_apos_cancelar(page, top_id_antes, timeout_ms=12000)
    if not ok_progresso:
        _grid_recovery(page)

    cancelados.append(dados)

    # ✅ persistência em tempo real
    try:
        anexar_cancelamento_e_persistir(ctx.wb, ctx.ws, ctx.xlsx_path, ctx.jsonl_path, dados)
    except Exception:
        pass

    page.wait_for_timeout(300)
    return True


def cancelar_tudo_da_unidade(ctx, unidade_label: str, cancelados: list[dict]) -> int:
    page = ctx.page
    cfg = ctx.config

    unidade_cod = unidade_codigo(unidade_label)
    total = 0
    zero_rounds = 0

    # ✅ watchdogs
    inicio_unidade = time.time()
    max_seg_por_unidade = getattr(cfg, "max_seg_por_unidade", 10 * 60)  # 10 minutos
    falhas_consecutivas_sem_progresso = 0
    max_falhas_sem_progresso = getattr(cfg, "max_falhas_sem_progresso", 10)

    # estabilidade inicial
    try:
        page.keyboard.press("Home")
        page.wait_for_timeout(250)
    except Exception:
        pass

    ctx.log(f"➡️ Entrando em cancelar_tudo_da_unidade ({unidade_cod})")

    while total < cfg.max_cancel_per_unit:
        # ✅ se estourou tempo, sai da unidade e vai pra próxima
        if (time.time() - inicio_unidade) > max_seg_por_unidade:
            ctx.log(f"⏱️ Timeout por unidade ({unidade_cod}) — saindo para próxima.")
            break

        state = esperar_grid_responder(
            page,
            grid_timeout_s=cfg.grid_timeout_s,
            poll_ms=cfg.grid_poll_ms,
            visible_scan_limit=cfg.visible_scan_limit,
        )

        if state == "NENHUM_DADO":
            break

        if state == "TIMEOUT" and (not tem_linhas_no_grid(page)):
            break

        cancelou_algum = False

        for _ in range(250):
            # watchdog dentro do loop também
            if (time.time() - inicio_unidade) > max_seg_por_unidade:
                break

            span, _, cod = achar_cancelar_permitido(page, scan_rows=max(20, cfg.visible_scan_limit))

            if span is None:
                scroll_grid(page)
                page.wait_for_timeout(250)

                falhas_consecutivas_sem_progresso += 1
                if falhas_consecutivas_sem_progresso >= max_falhas_sem_progresso:
                    ctx.log(f"⚠️ Muitas tentativas sem progresso ({unidade_cod}). Forçando recovery e saindo.")
                    _grid_recovery(page)
                    return total

                continue

            ok = cancelar_um_item_visivel(ctx, unidade_cod, cancelados)
            if not ok:
                falhas_consecutivas_sem_progresso += 1
                if falhas_consecutivas_sem_progresso >= max_falhas_sem_progresso:
                    ctx.log(f"⚠️ Falhas consecutivas ao cancelar ({unidade_cod}). Forçando recovery e saindo.")
                    _grid_recovery(page)
                    return total

                scroll_grid(page)
                page.wait_for_timeout(250)
                continue

            # ✅ cancelou de fato
            falhas_consecutivas_sem_progresso = 0
            total += 1
            cancelou_algum = True
            ctx.log(f"✅ Cancelado #{total} (unidade={unidade_cod}, codigo={cod})")

            # estabiliza rapidinho
            fechar_alert_sucesso(page)
            safe_networkidle_best_effort(page)
            page.wait_for_timeout(200)

        if cancelou_algum:
            zero_rounds = 0
        else:
            zero_rounds += 1
            page.wait_for_timeout(700)

        if zero_rounds >= cfg.zero_rounds_to_finish:
            break

    ctx.log(f"⬅️ Saindo de cancelar_tudo_da_unidade ({unidade_cod}) total={total}")
    return total


class NoShowStage(Stage):
    name = "no_show"

    def run(self, ctx) -> StageResult:
        page = ctx.page
        cfg = ctx.config

        ctx.log("\n🚚 Indo para tela No-Show...")
        goto_noshow(page)

        cancelados: list[dict] = []
        total_geral = 0

        for unidade in cfg.unidades:
            ctx.log(f"\n🏭 Selecionando unidade: {unidade}")
            fechar_alert_sucesso(page)
            selecionar_unidade(page, unidade)

            state = esperar_grid_responder(
                page,
                grid_timeout_s=cfg.grid_timeout_s,
                poll_ms=cfg.grid_poll_ms,
                visible_scan_limit=cfg.visible_scan_limit,
            )

            snap = debug_grid_snapshot(page)
            ctx.log(
                f"🔎 grid={snap['grid']} rows={snap['rows']} bans={snap['bans']} nenhum={snap['nenhum']} state={state}"
            )

            qtd = cancelar_tudo_da_unidade(ctx, unidade, cancelados)
            total_geral += qtd
            ctx.log(f"🧾 Total cancelado nesta unidade ({unidade_codigo(unidade)}): {qtd}")

        ctx.state["noshow_cancelados"] = cancelados
        return StageResult(name=self.name, ok=True, total=total_geral)