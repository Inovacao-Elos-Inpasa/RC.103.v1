from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from openpyxl import Workbook
from playwright.sync_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError

from .base import Stage, StageResult
from ..ui.apex import safe_networkidle, fechar_alert_sucesso, tentar_confirmacoes_genericas
from ..ui.nav import selecionar_unidade


# ============================================================
# Helpers resilientes / APEX / waits
# ============================================================
TRANSIENT_ERRORS = (
    "Execution context was destroyed",
    "most likely because of a navigation",
    "Target closed",
    "Frame was detached",
    "Cannot find context with specified id",
    "Navigation interrupted",
)


def _is_transient_playwright_error(exc: Exception) -> bool:
    msg = str(exc or "")
    return any(t in msg for t in TRANSIENT_ERRORS)


def retry_playwright(action, *, tentativas: int = 8, espera_ms: int = 800, on_retry=None, default=None):
    last_exc = None
    for tentativa in range(1, tentativas + 1):
        try:
            return action()
        except Exception as exc:
            last_exc = exc
            if not _is_transient_playwright_error(exc):
                raise
            if on_retry:
                try:
                    on_retry(tentativa, exc)
                except Exception:
                    pass
            time.sleep(espera_ms / 1000)

    if default is not None:
        return default
    raise last_exc


def safe_wait(page, ms: int = 300):
    try:
        page.wait_for_timeout(ms)
    except Exception:
        time.sleep(ms / 1000)


def safe_locator_count(locator, default: int = 0) -> int:
    try:
        return retry_playwright(lambda: locator.count(), default=default)
    except Exception:
        return default


def safe_is_visible(locator) -> bool:
    try:
        return retry_playwright(lambda: locator.is_visible(), default=False)
    except Exception:
        return False


def safe_text_content(locator, default: str = "") -> str:
    try:
        txt = retry_playwright(lambda: locator.text_content(), default=default)
        return txt or default
    except Exception:
        return default


def _aguardar_apex_idle_basico(page, timeout_ms: int = 20000):
    deadline = time.time() + (timeout_ms / 1000)

    while time.time() < deadline:
        try:
            busy = False

            for sel in ["#apex_wait_overlay", ".u-Processing", ".a-Processing"]:
                try:
                    loc = page.locator(sel).first
                    if safe_is_visible(loc):
                        busy = True
                        break
                except Exception:
                    pass

            if not busy:
                return

            safe_wait(page, 300)

        except Exception as exc:
            if _is_transient_playwright_error(exc):
                safe_wait(page, 500)
                continue
            raise


def esperar_kanban_pronto(page, timeout_ms: int = 45000):
    deadline = time.time() + (timeout_ms / 1000)
    ultimo_erro = None

    while time.time() < deadline:
        try:
            page.locator("#kb-painel-carregamento").first.wait_for(state="visible", timeout=8000)
            _aguardar_apex_idle_basico(page, timeout_ms=8000)

            try:
                safe_networkidle(page)
            except Exception:
                pass

            safe_wait(page, 400)

            if safe_is_visible(page.locator("#kb-painel-carregamento").first):
                return

        except Exception as exc:
            ultimo_erro = exc
            if _is_transient_playwright_error(exc):
                safe_wait(page, 800)
            else:
                safe_wait(page, 500)

    if ultimo_erro:
        raise ultimo_erro


def _header_cancelado_text(page) -> str:
    def _read():
        root = page.locator("#kb-painel-carregamento")
        b = root.locator(".kb-col-header#C .kb-col-header-content p.title b").first
        return (safe_text_content(b, "") or "").strip()

    try:
        return retry_playwright(_read, default="")
    except Exception:
        return ""


def esperar_refresh_kanban(page, prev_cancelado_text: str | None, timeout_ms: int = 45000):
    deadline = time.time() + (timeout_ms / 1000)

    while time.time() < deadline:
        try:
            esperar_kanban_pronto(page, timeout_ms=12000)
        except Exception:
            safe_wait(page, 500)

        cur = _header_cancelado_text(page)

        if prev_cancelado_text is None:
            return

        if cur and cur != prev_cancelado_text:
            return

        safe_wait(page, 350)

    return


# ============================================================
# Navegação Menu: Transporte > Carregamento > Painel
# ============================================================
def goto_painel_carregamento(page):
    fechar_alert_sucesso(page)
    _aguardar_apex_idle_basico(page)

    def _open_menu():
        transporte = page.locator("span[role='treeitem'][aria-level='1']", has_text="Transporte").first
        transporte.wait_for(state="visible", timeout=30000)

        expanded = None
        try:
            expanded = transporte.get_attribute("aria-expanded")
        except Exception:
            pass

        if expanded != "true":
            try:
                transporte.click(timeout=5000)
            except Exception:
                transporte.click(force=True)

        safe_wait(page, 300)

        carreg = page.locator("span.a-TreeView-label[aria-level='2']", has_text="Carregamento").first
        carreg.wait_for(state="visible", timeout=30000)

        expanded = None
        try:
            expanded = carreg.get_attribute("aria-expanded")
        except Exception:
            pass

        if expanded != "true":
            try:
                carreg.click(timeout=5000)
            except Exception:
                carreg.click(force=True)

        safe_wait(page, 300)

        # painel = page.locator("#t_TreeNav_20 a.a-TreeView-label", has_text="Painel").first
        painel = page.locator('a.a-TreeView-label[href*="painel-carregamento"]', has_text="Painel")
        painel.wait_for(state="visible", timeout=30000)

        try:
            with page.expect_navigation(wait_until="domcontentloaded", timeout=45000):
                painel.click()
        except Exception:
            try:
                painel.click(force=True)
            except Exception:
                painel.evaluate("el => el.click()")

    retry_playwright(_open_menu, tentativas=5, espera_ms=1200)
    esperar_kanban_pronto(page)


# ============================================================
# Filtros: D-1, Produto, Filtrar
# ============================================================
# ✅ Produtos a consultar (ordem importa)
PRODUTOS_CONSULTA = [
    ("5", "5 - FARELO DE MILHO (DDGS)"),
    ("41", "41 - FARELO DE MILHO"),
    ("154", "154 - FARELO DE MILHO (DDGS) MI"),
    ("159", "159 - FARELO DE SORGO"),
]


def abrir_filtros(page):
    btn = page.locator("#filtros").first
    btn.wait_for(state="visible", timeout=30000)
    retry_playwright(lambda: btn.click(timeout=5000), tentativas=5, espera_ms=800)

    page.locator("#P650_DATA_INICIAL_input").first.wait_for(state="visible", timeout=30000)
    page.locator("#P650_DATA_FINAL_input").first.wait_for(state="visible", timeout=30000)
    page.locator("#P650_ITEM").first.wait_for(state="visible", timeout=30000)


def _fill_date_input(page, selector: str, value: str):
    def _do():
        inp = page.locator(selector).first
        inp.wait_for(state="visible", timeout=20000)
        inp.click()
        inp.fill("")
        inp.type(value, delay=15)

    try:
        retry_playwright(_do, tentativas=5, espera_ms=700)
    except Exception:
        page.locator(selector).first.fill(value)


def preencher_datas_d1(page):
    d1 = (datetime.now() - timedelta(days=1)).strftime("%d/%m/%Y")
    _fill_date_input(page, "#P650_DATA_INICIAL_input", d1)
    _fill_date_input(page, "#P650_DATA_FINAL_input", d1)


def _fechar_dialog_lov_produto(page) -> bool:
    try:
        btn = page.locator(
            "button.ui-dialog-titlebar-close, "
            "button.ui-button.ui-corner-all.ui-widget.ui-button-icon-only.ui-dialog-titlebar-close"
        ).first

        if safe_is_visible(btn):
            retry_playwright(lambda: btn.click(force=True), default=None)
            safe_wait(page, 250)
            return True
    except Exception:
        pass

    try:
        page.keyboard.press("Escape")
        safe_wait(page, 250)
        return True
    except Exception:
        return False


def selecionar_produto_popup_lov(page, produto_id: str, produto_texto: str | None = None) -> bool:
    """
    Campo readonly (#P650_ITEM) abre dialog. Seleciona o produto.
    ✅ Se lista vazia / não encontrou produto => fecha no X e retorna False.
    ✅ Agora suporta qualquer produto (ex: 41, 159).
    """
    campo = page.locator("#P650_ITEM").first
    campo.wait_for(state="visible", timeout=20000)

    try:
        campo.click(timeout=5000)
    except Exception:
        campo.click(force=True)

    dialog = page.locator("[role='dialog']").last
    dialog.wait_for(state="visible", timeout=30000)

    def _find_item():
        it = dialog.locator(f"li[data-id='{produto_id}']").first
        if safe_locator_count(it) > 0:
            return it

        it = dialog.locator("li", has_text=f"{produto_id} -").first
        if safe_locator_count(it) > 0:
            return it

        if produto_texto:
            it = dialog.locator("li", has_text=produto_texto).first
            if safe_locator_count(it) > 0:
                return it

        return None

    def _lista_vazia():
        alt = dialog.locator("span.a-GV-altMessage-text", has_text="Nenhum resultado encontrado.").first
        return safe_is_visible(alt)

    def _wait_list_settle(timeout_ms=12000):
        deadline = time.time() + (timeout_ms / 1000)
        while time.time() < deadline:
            try:
                item = _find_item()
                if item is not None:
                    return True
                if _lista_vazia():
                    return True
                if safe_locator_count(dialog.locator("li")) > 0:
                    return True
            except Exception:
                pass
            safe_wait(page, 250)
        return False

    def _set_search(texto: str) -> bool:
        try:
            search = dialog.locator("input[type='search']").first
            if safe_locator_count(search) == 0:
                search = dialog.locator("input[type='text']").first

            if safe_locator_count(search) > 0 and safe_is_visible(search):
                search.click()
                search.fill("")
                if texto:
                    search.type(texto, delay=20)
                safe_wait(page, 350)
                return True
        except Exception:
            pass
        return False

    _wait_list_settle(timeout_ms=12000)

    # ✅ tentativas mais assertivas para garantir seleção
    tentativas = [
        produto_texto or "",     # ex: "41 - FARELO DE MILHO"
        f"{produto_id}",         # ex: "41"
        f"{produto_id} -",       # ex: "41 -"
        "",                      # lista inteira
    ]

    for t in tentativas:
        _set_search(t)
        _wait_list_settle(timeout_ms=12000)

        item = _find_item()
        if item is not None:
            try:
                item.wait_for(state="visible", timeout=8000)
                item.scroll_into_view_if_needed(timeout=5000)
            except Exception:
                pass

            try:
                retry_playwright(lambda: item.click(timeout=7000), tentativas=4, espera_ms=700)
            except Exception:
                try:
                    item.click(force=True, timeout=7000)
                except Exception:
                    try:
                        item.evaluate("el => el.click()")
                    except Exception:
                        tentar_confirmacoes_genericas(page)

            try:
                dialog.wait_for(state="hidden", timeout=20000)
            except Exception:
                _fechar_dialog_lov_produto(page)

            return True

        if _lista_vazia():
            continue

    _fechar_dialog_lov_produto(page)
    return False


def clicar_filtrar(page) -> bool:
    btn = page.locator("#B9644535394150771945").first

    try:
        btn.wait_for(state="attached", timeout=20000)
    except Exception:
        return False

    try:
        btn.scroll_into_view_if_needed(timeout=5000)
    except Exception:
        pass

    try:
        retry_playwright(lambda: btn.click(timeout=7000), tentativas=5, espera_ms=900)
        return True
    except Exception:
        try:
            btn.click(force=True, timeout=7000)
            return True
        except Exception:
            try:
                btn.evaluate("el => el.click()")
                return True
            except Exception:
                return False


def aplicar_filtros_painel(page, produto_id: str, produto_texto: str | None = None) -> bool:
    """
    Retorna True se produto selecionado e filtro aplicado.
    Retorna False se produto não existir / lista vazia.
    """
    esperar_kanban_pronto(page)

    prev = None
    try:
        prev = _header_cancelado_text(page) or None
    except Exception:
        prev = None

    abrir_filtros(page)
    preencher_datas_d1(page)

    ok_produto = selecionar_produto_popup_lov(page, produto_id, produto_texto=produto_texto)
    if not ok_produto:
        clicar_filtrar(page)  # tenta mesmo assim (não trava se falhar)
        tentar_confirmacoes_genericas(page)
        return False

    clicar_filtrar(page)
    esperar_refresh_kanban(page, prev_cancelado_text=prev)
    return True


# ============================================================
# Kanban: Cancelado (C) + cards + extrações
# ============================================================
def qtd_cancelado_header(page) -> int:
    txt = _header_cancelado_text(page)
    try:
        return int(txt) if txt else 0
    except Exception:
        return 0


def cards_cancelado(page):
    root = page.locator("#kb-painel-carregamento")
    cont = root.locator(".kb-item-container[columnid='C']").first
    return cont.locator(".kb-card")


def _text_clean(s: str) -> str:
    return " ".join((s or "").replace("\u00a0", " ").split()).strip()


def _card_field_by_div(card, div_class: str, value_class: str = ".kb-card-info") -> str:
    try:
        loc = card.locator(f"div.{div_class} {value_class}").first
        if safe_locator_count(loc) > 0:
            return _text_clean(safe_text_content(loc, ""))
    except Exception:
        pass
    return ""


def _card_field_by_class_nth(card, div_class: str, index: int = 0) -> str:
    try:
        divs = card.locator(f"div.{div_class}")
        if safe_locator_count(divs) <= index:
            return ""
        div = divs.nth(index)

        info = div.locator(".kb-card-info").first
        if safe_locator_count(info) > 0:
            return _text_clean(safe_text_content(info, ""))

        return _text_clean(div.inner_text() or "")
    except Exception:
        return ""


def _card_field_placas(card) -> tuple[str, str]:
    """
    No HTML: aparecem duas div.placa:
      - 1ª: Cavalo
      - 2ª: Reboque(s)
    """
    try:
        placas = card.locator("div.placa .kb-card-info")
        qtd = safe_locator_count(placas)
        if qtd >= 2:
            return (_text_clean(safe_text_content(placas.nth(0), "")),
                    _text_clean(safe_text_content(placas.nth(1), "")))
        if qtd == 1:
            return (_text_clean(safe_text_content(placas.nth(0), "")), "")
    except Exception:
        pass
    return ("", "")


def extrair_dados_card(card) -> dict:
    cavalo, reboques = _card_field_placas(card)
    return {
        "Data": _card_field_by_div(card, "dh-evento", ".kb-card-info-ev"),
        "Agendamento": _card_field_by_div(card, "num-agend"),
        "NomeCliente": _card_field_by_div(card, "ordemretiradacliente"),
        "Pedido": _card_field_by_div(card, "nr-ped"),
        "Produto": _card_field_by_div(card, "itens-ped"),
        "Periodo": _card_field_by_div(card, "per-carr"),
        "Transportadora": _card_field_by_class_nth(card, "transp", index=1),
        "Motorista": _card_field_by_div(card, "motorista"),
        "Cavalo": cavalo,
        "Reboques": reboques,
    }


def abrir_dialog_do_card(page, card):
    def _click_card():
        a = card.locator("a").first
        a.wait_for(state="visible", timeout=30000)
        try:
            a.click(timeout=7000)
        except Exception:
            try:
                a.click(force=True, timeout=7000)
            except Exception:
                a.evaluate("el => el.click()")

    retry_playwright(_click_card, tentativas=6, espera_ms=1200)

    retry_playwright(
        lambda: page.locator("iframe[title*='Painel Carregamento']").first.wait_for(
            state="visible",
            timeout=15000
        ),
        tentativas=6,
        espera_ms=1000,
    )

    _aguardar_apex_idle_basico(page)
    safe_wait(page, 300)


def fechar_dialog(page):
    try:
        page.keyboard.press("Escape")
        safe_wait(page, 250)
    except Exception:
        pass

    for sel in [
        "button[aria-label='Close']",
        "button[title='Close']",
        "button.ui-dialog-titlebar-close",
        "button.t-Dialog-closeButton",
    ]:
        try:
            b = page.locator(sel).first
            if safe_locator_count(b) > 0 and safe_is_visible(b):
                retry_playwright(lambda: b.click(force=True), default=None)
                safe_wait(page, 250)
                break
        except Exception:
            pass

    try:
        retry_playwright(
            lambda: page.locator("iframe[title*='Painel Carregamento']").first.wait_for(
                state="hidden",
                timeout=30000
            ),
            tentativas=4,
            espera_ms=700,
            default=None,
        )
    except Exception:
        pass


def extrair_motivo_cancelamento_iframe(page) -> str:
    iframe = page.locator("iframe[title*='Painel Carregamento']").first
    retry_playwright(lambda: iframe.wait_for(state="visible", timeout=45000), tentativas=6, espera_ms=1000)

    fl = page.frame_locator("iframe[title*='Painel Carregamento']")

    try:
        item = fl.locator(
            ".t-ContextualInfo-item",
            has=fl.locator(".t-ContextualInfo-label", has_text="Motivo Cancelamento"),
        ).first
        if safe_locator_count(item) > 0:
            val = item.locator(".t-ContextualInfo-value").first
            if safe_locator_count(val) > 0:
                return _text_clean(safe_text_content(val, ""))
    except Exception:
        pass

    try:
        region = fl.locator("[role='region'][aria-label='Motivo Cancelamento']").first
        if safe_locator_count(region) > 0:
            item2 = region.locator(
                ".t-ContextualInfo-item",
                has=region.locator(".t-ContextualInfo-label", has_text="Motivo Cancelamento"),
            ).first
            if safe_locator_count(item2) > 0:
                val2 = item2.locator(".t-ContextualInfo-value").first
                if safe_locator_count(val2) > 0:
                    return _text_clean(safe_text_content(val2, ""))
    except Exception:
        pass

    return ""


# ============================================================
# Relatórios: JSON + Excel
# ============================================================
CAMPOS_EXCEL = [
    "Unidade",
    "Data",
    "Agendamento",
    "NomeCliente",
    "Pedido",
    "Produto",
    "Periodo",
    "Transportadora",
    "Motorista",
    "Cavalo",
    "Reboques",
    "MotivoCancelamento",
]


def salvar_json(path: str, data: list[dict]):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# def salvar_excel(path: str, data: list[dict]):
#     wb = Workbook()
#     ws = wb.active
#     ws.title = "Cancelamentos"

#     ws.append(CAMPOS_EXCEL)
#     for row in data:
#         ws.append([row.get(c, "") for c in CAMPOS_EXCEL])

#     wb.save(path)

def salvar_excel(path: str, data: list[dict]):
    wb = Workbook()
    ws = wb.active
    ws.title = "Cancelamentos"

    # Agrupa por Unidade (mantendo a ordem de aparição)
    ordem_unidades: list[str] = []
    grupos: dict[str, list[dict]] = {}

    for row in data:
        un = row.get("Unidade", "") or ""
        if un not in grupos:
            grupos[un] = []
            ordem_unidades.append(un)
        grupos[un].append(row)

    # Se não tiver dados, ainda assim coloca um cabeçalho
    if not data:
        ws.append(CAMPOS_EXCEL)
        wb.save(path)
        return

    # Escreve por unidade, repetindo o cabeçalho a cada troca
    for idx, unidade in enumerate(ordem_unidades):
        # linha em branco entre blocos (não antes do primeiro)
        if idx > 0:
            ws.append([])

        # cabeçalho do bloco
        ws.append(CAMPOS_EXCEL)

        # linhas do bloco
        for row in grupos[unidade]:
            ws.append([row.get(c, "") for c in CAMPOS_EXCEL])

    wb.save(path)


# ============================================================
# Kanban robusto: snapshot / recovery / leitura sem count
# ============================================================
def _kanban_root(page):
    return page.locator("#kb-painel-carregamento").first


def _kanban_cancelado_container(page):
    return _kanban_root(page).locator(".kb-item-container[columnid='C']").first


def _kanban_recovery(page):
    try:
        page.keyboard.press("Escape")
        safe_wait(page, 200)
    except Exception:
        pass

    fechar_alert_sucesso(page)
    try:
        tentar_confirmacoes_genericas(page)
    except Exception:
        pass

    _aguardar_apex_idle_basico(page)
    try:
        safe_networkidle(page)
    except Exception:
        pass
    safe_wait(page, 350)

    try:
        _kanban_cancelado_container(page).evaluate(
            """el => {
                el.scrollTop = 0;
                el.scrollBy(0, 120);
            }"""
        )
        safe_wait(page, 250)
    except Exception:
        pass


def _snapshot_cards_cancelado(page) -> list[dict]:
    js = r"""
    (el) => {
      const txt = (root, sel) => {
        const n = root.querySelector(sel);
        return ((n && n.textContent) || '').replace(/ /g, ' ').replace(/\s+/g, ' ').trim();
      };
      return Array.from(el.querySelectorAll('.kb-card')).map((card, idx) => {
        const ag = txt(card, '.num-agend .kb-item-value, .num-agend');
        const nome = txt(card, '.ordemretiradacliente .kb-item-value, .ordemretiradacliente');
        const pedido = txt(card, '.nr-ped .kb-item-value, .nr-ped');
        const produto = txt(card, '.itens-ped .kb-item-value, .itens-ped');
        return {
          index: idx,
          agendamento: ag,
          nome_cliente: nome,
          pedido: pedido,
          produto: produto,
          assinatura: [ag, nome, pedido, produto].filter(Boolean).join(' | '),
        };
      });
    }
    """
    try:
        return retry_playwright(
            lambda: _kanban_cancelado_container(page).evaluate(js),
            tentativas=8,
            espera_ms=900,
            default=[],
        ) or []
    except Exception:
        return []


def _assinatura_card_dict(card_info: dict) -> str:
    parts = [
        str(card_info.get("agendamento") or "").strip(),
        str(card_info.get("nome_cliente") or "").strip(),
        str(card_info.get("pedido") or "").strip(),
        str(card_info.get("produto") or "").strip(),
    ]
    parts = [p for p in parts if p]
    return " | ".join(parts)


def _localizar_card_por_assinatura(page, card_info: dict):
    agendamento = str(card_info.get("agendamento") or "").strip()
    assinatura = _assinatura_card_dict(card_info)
    cont = _kanban_cancelado_container(page)

    candidatos = []
    if assinatura:
        candidatos.append(cont.locator(".kb-card", has_text=assinatura).first)
    if agendamento:
        candidatos.append(cont.locator(".kb-card", has_text=agendamento).first)
    idx = card_info.get("index")
    if isinstance(idx, int):
        candidatos.append(cont.locator(".kb-card").nth(idx))

    for cand in candidatos:
        try:
            anc = cand.locator("a").first
            retry_playwright(lambda: anc.wait_for(state="visible", timeout=3000), tentativas=2, espera_ms=350)
            return cand
        except Exception:
            continue

    return None


def _ler_card_por_snapshot(page, card_info: dict) -> dict | None:
    card = _localizar_card_por_assinatura(page, card_info)
    if card is None:
        return None

    dados = retry_playwright(
        lambda: extrair_dados_card(card),
        tentativas=4,
        espera_ms=700,
        default={},
    )

    def _abrir_e_ler():
        abrir_dialog_do_card(page, card)
        try:
            return extrair_motivo_cancelamento_iframe(page)
        finally:
            fechar_dialog(page)

    motivo = retry_playwright(
        _abrir_e_ler,
        tentativas=5,
        espera_ms=1000,
        default="",
    )

    dados["MotivoCancelamento"] = motivo or ""
    return dados


def coletar_cancelados_do_produto(ctx, unidade: str, produto_id: str, produto_texto: str, resultados: list[dict]):
    page = ctx.page

    ctx.log(f"🔎 Aplicando filtro do produto: {produto_texto}")
    ok_prod = aplicar_filtros_painel(page, produto_id=produto_id, produto_texto=produto_texto)
    if not ok_prod:
        ctx.log("⚠️ Produto não disponível (lista vazia / não encontrado). Pulando este produto.")
        return

    qtd_header = qtd_cancelado_header(page)
    ctx.log(f"📌 Cancelado (header) nesta unidade: {qtd_header}")
    if qtd_header == 0:
        ctx.log("ℹ️ Header Cancelado = 0. Seguindo para o próximo produto/unidade.")
        return

    processados: set[str] = set()
    rounds_sem_progresso = 0
    max_rounds_sem_progresso = 3
    max_itens_esperados = max(qtd_header + 2, qtd_header)

    while len(processados) < max_itens_esperados and rounds_sem_progresso < max_rounds_sem_progresso:
        retry_playwright(
            lambda: esperar_kanban_pronto(page, timeout_ms=30000),
            tentativas=6,
            espera_ms=900,
            on_retry=lambda t, e: ctx.log(f"⏳ Aguardando estabilização do kanban (tentativa {t})"),
            default=None,
        )

        snapshot = _snapshot_cards_cancelado(page)
        if not snapshot:
            rounds_sem_progresso += 1
            _kanban_recovery(page)
            continue

        pendentes = []
        for item in snapshot:
            assinatura = _assinatura_card_dict(item)
            chave = assinatura or f"idx:{item.get('index')}"
            if chave in processados:
                continue
            pendentes.append((chave, item))

        if not pendentes:
            rounds_sem_progresso += 1
            try:
                _kanban_cancelado_container(page).evaluate("el => el.scrollBy(0, 220)")
            except Exception:
                pass
            safe_wait(page, 300)
            continue

        houve_progresso = False
        for chave, item in pendentes:
            try:
                dados = _ler_card_por_snapshot(page, item)
                if not dados:
                    continue

                dados["Unidade"] = unidade
                dados.setdefault("MotivoCancelamento", "")
                resultados.append(dados)
                processados.add(chave)
                houve_progresso = True
                ctx.log(
                    f"✅ Capturado #{len(resultados)} (unidade={unidade}, agendamento={dados.get('Agendamento', '')})"
                )
            except Exception as e:
                ctx.log(f"⚠️ Falha ao ler card do produto {produto_id}: {e}")
                _kanban_recovery(page)

        if houve_progresso:
            rounds_sem_progresso = 0
        else:
            rounds_sem_progresso += 1
            _kanban_recovery(page)

    if len(processados) < qtd_header:
        ctx.log(
            f"⚠️ Foram capturados {len(processados)} de {qtd_header} cancelados visíveis para {produto_texto}."
        )


# ============================================================
# Stage
# ============================================================
class CancelamentoStage(Stage):
    name = "cancelamento"

    def run(self, ctx) -> StageResult:
        page = ctx.page
        cfg = ctx.config

        ctx.log("\n🚚 Indo para Painel Carregamento...")
        goto_painel_carregamento(page)

        resultados: list[dict] = []
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        pasta = Path("relatorios/cancelamentos")
        pasta.mkdir(parents=True, exist_ok=True)

        json_path = pasta / f"cancelamentos_{stamp}.json"
        xlsx_path = pasta / f"cancelamentos_{stamp}.xlsx"

        for unidade in cfg.unidades:
            ctx.log(f"\n🏭 Selecionando unidade: {unidade}")
            fechar_alert_sucesso(page)

            try:
                selecionar_unidade(page, unidade)
            except Exception as e:
                ctx.log(f"⚠️ Falha ao selecionar unidade {unidade}: {e}")
                _kanban_recovery(page)
                continue

            retry_playwright(
                lambda: esperar_kanban_pronto(page, timeout_ms=45000),
                tentativas=6,
                espera_ms=1000,
                default=None,
            )

            for produto_id, produto_texto in PRODUTOS_CONSULTA:
                try:
                    coletar_cancelados_do_produto(ctx, unidade, produto_id, produto_texto, resultados)
                except Exception as e:
                    ctx.log(f"⚠️ Falha ao processar produto {produto_texto} na unidade {unidade}: {e}")
                    _kanban_recovery(page)

                safe_wait(page, 500)

            safe_wait(page, 700)

        salvar_json(str(json_path), resultados)
        salvar_excel(str(xlsx_path), resultados)

        ctx.log(f"\n🧾 JSON gerado: {json_path}")
        ctx.log(f"📄 Excel gerado: {xlsx_path}")

        ctx.state["cancelamentos_json_path"] = str(json_path)
        ctx.state["cancelamentos_xlsx_path"] = str(xlsx_path)
        ctx.state["cancelamentos_itens"] = resultados

        return StageResult(
            name=self.name,
            ok=True,
            total=len(resultados),
            details=f"json={json_path} xlsx={xlsx_path}",
        )
