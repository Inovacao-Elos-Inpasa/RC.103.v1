# import re
# import time
# from datetime import datetime, timedelta

# from .base import Stage, StageResult
# from ..ui.apex import safe_networkidle, fechar_alert_sucesso
# from ..ui.nav import selecionar_unidade, goto_distribuicao_comercial


# UNIDADE_SINOP = "1.1.1 - INPASA SINOP/MT"
# PRODUTO_41_TEXTO = "41 - FARELO DE MILHO (DDGS)"
# PRODUTO_41_ID = "41"


# # =========================
# # Utils
# # =========================
# def _d_minus_1_str() -> str:
#     return (datetime.now() - timedelta(days=1)).strftime("%d/%m/%Y")


# def _aguardar_apex_idle_basico(page):
#     # overlays comuns do APEX
#     for sel in ["#apex_wait_overlay", ".u-Processing", ".a-Processing"]:
#         try:
#             loc = page.locator(sel)
#             if loc.count() > 0:
#                 loc.first.wait_for(state="hidden", timeout=20000)
#         except Exception:
#             pass


# def _aguardar_tela_estabilizar(page, timeout_ms: int = 30000):
#     """
#     Melhor esforço: espera overlays sumirem + safe_networkidle (se não travar)
#     """
#     _aguardar_apex_idle_basico(page)
#     try:
#         safe_networkidle(page)
#     except Exception:
#         pass
#     _aguardar_apex_idle_basico(page)
#     page.wait_for_timeout(350)


# def _click_checkbox_and_wait(page, selector: str):
#     """
#     Clica e aguarda a tela estabilizar (APEX costuma submeter/refresh)
#     """
#     cb = page.locator(selector).first
#     cb.wait_for(state="visible", timeout=20000)
#     cb.click(force=True)
#     _aguardar_tela_estabilizar(page)


# def _is_checked(page, selector: str) -> bool:
#     cb = page.locator(selector).first
#     try:
#         cb.wait_for(state="attached", timeout=20000)
#     except Exception:
#         return False

#     try:
#         # Em input checkbox, o Playwright suporta is_checked()
#         return cb.is_checked()
#     except Exception:
#         # fallback por atributo "checked"
#         try:
#             return cb.get_attribute("checked") is not None
#         except Exception:
#             return False


# # =========================
# # P520
# # =========================
# def _set_date_d_minus_1(page):
#     d1 = _d_minus_1_str()

#     inp = page.locator("#P520_DATA_INICIAL_input")
#     inp.wait_for(state="visible", timeout=20000)

#     inp.click()
#     inp.fill("")
#     inp.type(d1, delay=20)
#     page.keyboard.press("Enter")
#     page.wait_for_timeout(400)


# def _abrir_lov_produto(page):
#     fechar_alert_sucesso(page)

#     btn = page.locator("#P520_COD_PRODUTO_lov_btn")
#     btn.wait_for(state="visible", timeout=20000)
#     btn.click(force=True)

#     page.wait_for_timeout(300)

#     lista = page.locator("ul.a-IconList[role='listbox']").last
#     lista.wait_for(state="visible", timeout=20000)
#     return lista


# def _select_produto_41_lov(page):
#     lista = _abrir_lov_produto(page)

#     item = lista.locator(f"li.a-IconList-item[data-id='{PRODUTO_41_ID}']")
#     if item.count() > 0:
#         item.first.click(force=True)
#         _aguardar_tela_estabilizar(page)
#         return

#     item2 = lista.locator("li.a-IconList-item", has_text=PRODUTO_41_TEXTO)
#     if item2.count() > 0:
#         item2.first.click(force=True)
#         _aguardar_tela_estabilizar(page)
#         return

#     raise RuntimeError("Produto 41 não encontrado no LOV.")


# def _click_filtros(page):
#     page.locator("#B1969627570211181615").click(force=True)
#     page.wait_for_timeout(600)


# def _click_filtrar_p520(page):
#     loc = page.locator("button", has_text=re.compile(r"^\s*Filtrar\s*$", re.I))
#     loc.first.wait_for(state="visible", timeout=20000)
#     loc.first.click(force=True)
#     _aguardar_tela_estabilizar(page)


# def _aplicar_checks_pos_filtrar(page):
#     """
#     Depois de filtrar:
#       - marca "Com distribuição"
#       - desmarca "Com saldo" se estiver marcado
#       - desmarca "Somente ativos" se estiver marcado
#     E aguarda a tela carregar após cada alteração.
#     """
#     # ✅ marcar "Com distribuição" (se ainda não estiver marcado)
#     if not _is_checked(page, "#P520_PEDIDOS_COM_DISTRIB"):
#         _click_checkbox_and_wait(page, "#P520_PEDIDOS_COM_DISTRIB")
#     else:
#         _aguardar_tela_estabilizar(page)

#     # ✅ desmarcar "Com saldo" se estiver marcado
#     if _is_checked(page, "#P520_SOMENTE_PEDIDOS_SALDO"):
#         _click_checkbox_and_wait(page, "#P520_SOMENTE_PEDIDOS_SALDO")
#     else:
#         _aguardar_tela_estabilizar(page)

#     # ✅ desmarcar "Somente ativos" se estiver marcado
#     if _is_checked(page, "#P520_SOMENTE_ATIVOS"):
#         _click_checkbox_and_wait(page, "#P520_SOMENTE_ATIVOS")
#     else:
#         _aguardar_tela_estabilizar(page)


# def _verificar_coluna_data_d_minus_1(page):
#     """
#     Procura SOMENTE o header que contém a data D-1 e imprime o texto do header.
#     Não varre todas as colunas manualmente.
#     """
#     data_d1 = _d_minus_1_str()

#     # aguarda a região da IRR aparecer (headers)
#     page.wait_for_selector("th.a-IRR-header", timeout=20000)

#     header = page.locator("th.a-IRR-header", has_text=data_d1).first

#     if header.count() > 0:
#         texto = (header.inner_text() or "").strip()
#         print(f"\n✅ Coluna encontrada para D-1 ({data_d1}):\n{texto}\n")
#         return texto

#     print(f"\n⚠️ Coluna com data D-1 ({data_d1}) não encontrada.\n")
#     return None


# # =========================
# # STAGE
# # =========================
# class Produto41Stage(Stage):
#     name = "produto_41"

#     def run(self, ctx) -> StageResult:
#         page = ctx.page

#         try:
#             ctx.log("🧪 Produto 41")

#             goto_distribuicao_comercial(page)

#             fechar_alert_sucesso(page)
#             _aguardar_tela_estabilizar(page)

#             ctx.log("🏭 Unidade SINOP")
#             selecionar_unidade(page, UNIDADE_SINOP)
#             _aguardar_tela_estabilizar(page)

#             ctx.log("🧰 Filtros")
#             _click_filtros(page)

#             ctx.log("📅 Data D-1")
#             _set_date_d_minus_1(page)
#             _aguardar_tela_estabilizar(page)

#             ctx.log("📦 Produto 41")
#             _select_produto_41_lov(page)

#             ctx.log("🔎 Filtrar P520")
#             _click_filtrar_p520(page)

#             ctx.log("☑️ Ajustando checkboxes pós-filtrar")
#             _aplicar_checks_pos_filtrar(page)

#             ctx.log("📌 Verificando coluna D-1")
#             _verificar_coluna_data_d_minus_1(page)

#             ctx.log("✅ Sucesso")

#             return StageResult(
#                 name=self.name,
#                 ok=True,
#                 total=0,
#                 details="Produto 41 executado com sucesso.",
#             )

#         except Exception as e:
#             ctx.log("❌ Erro:", repr(e))
#             return StageResult(name=self.name, ok=False, total=0, details=str(e))

from __future__ import annotations

import re
import time
from datetime import datetime, timedelta

from .base import Stage, StageResult
from ..ui.apex import safe_networkidle, fechar_alert_sucesso
from ..ui.nav import selecionar_unidade, goto_distribuicao_comercial


UNIDADE_SINOP = "1.1.1 - INPASA SINOP/MT"
PRODUTO_41_TEXTO = "41 - FARELO DE MILHO (DDGS)"
PRODUTO_41_ID = "41"


# =========================
# Utils
# =========================
def _d_minus_1_str() -> str:
    return (datetime.now() - timedelta(days=1)).strftime("%d/%m/%Y")


def _aguardar_apex_idle_basico(page):
    for sel in ["#apex_wait_overlay", ".u-Processing", ".a-Processing"]:
        try:
            loc = page.locator(sel)
            if loc.count() > 0:
                loc.first.wait_for(state="hidden", timeout=15000)
        except Exception:
            pass


def _aguardar_refresh_tela(page, timeout_ms: int = 20000):
    """
    Best effort: espera overlays sumirem e dá um pequeno settle.
    """
    _aguardar_apex_idle_basico(page)
    try:
        safe_networkidle(page)
    except Exception:
        pass
    page.wait_for_timeout(400)


# =========================
# P520 (Filtros e Produto)
# =========================
def _set_date_d_minus_1(page):
    d1 = _d_minus_1_str()

    inp = page.locator("#P520_DATA_INICIAL_input")
    inp.wait_for(state="visible", timeout=20000)

    inp.click()
    inp.fill("")
    inp.type(d1, delay=20)
    page.keyboard.press("Enter")
    _aguardar_refresh_tela(page)


def _abrir_lov_produto(page):
    fechar_alert_sucesso(page)

    btn = page.locator("#P520_COD_PRODUTO_lov_btn")
    btn.wait_for(state="visible", timeout=20000)
    btn.click(force=True)

    page.wait_for_timeout(300)

    lista = page.locator("ul.a-IconList[role='listbox']").last
    lista.wait_for(state="visible", timeout=20000)
    return lista


def _select_produto_41_lov(page):
    lista = _abrir_lov_produto(page)

    item = lista.locator(f"li.a-IconList-item[data-id='{PRODUTO_41_ID}']")
    if item.count() > 0:
        item.first.click(force=True)
        _aguardar_refresh_tela(page)
        return

    item2 = lista.locator("li.a-IconList-item", has_text=PRODUTO_41_TEXTO)
    if item2.count() > 0:
        item2.first.click(force=True)
        _aguardar_refresh_tela(page)
        return

    raise RuntimeError("Produto 41 não encontrado no LOV.")


def _click_filtros(page):
    page.locator("#B1969627570211181615").click(force=True)
    page.wait_for_timeout(600)


def _click_filtrar_p520(page):
    loc = page.locator("button", has_text=re.compile(r"^\s*Filtrar\s*$", re.I))
    loc.first.click(force=True)


# =========================
# Pós-filtrar: checkboxes
# =========================
def _set_checkbox(page, selector: str, checked: bool, label: str):
    cb = page.locator(selector).first
    cb.wait_for(state="visible", timeout=20000)

    def _is_checked() -> bool:
        try:
            return cb.is_checked()
        except Exception:
            # fallback: atributo checked
            try:
                return cb.get_attribute("checked") is not None
            except Exception:
                return False

    atual = _is_checked()
    if atual == checked:
        return

    page.wait_for_timeout(250)
    cb.click(force=True)
    _aguardar_refresh_tela(page)
    fechar_alert_sucesso(page)


def _ajustar_checkboxes_pos_filtrar(page):
    print("☑️ Ajustando checkboxes pós-filtrar")
    # Clicar em "Com distribuição" (queremos marcar)
    _set_checkbox(page, "#P520_PEDIDOS_COM_DISTRIB", True, "Com distribuição")

    # Se estiver checado, tirar check dos 2 abaixo
    _set_checkbox(page, "#P520_SOMENTE_PEDIDOS_SALDO", False, "Com saldo")
    _set_checkbox(page, "#P520_SOMENTE_ATIVOS", False, "Somente ativos")


# =========================
# ✅ NOVO: achar coluna D-1 e ler linha a linha
# =========================
def _achar_header_id_data_d_minus_1(page) -> str | None:
    data_d1 = _d_minus_1_str()

    try:
        page.wait_for_selector("th.a-IRR-header", timeout=20000)
    except Exception:
        print("⚠️ Não encontrei th.a-IRR-header, vou tentar achar <th> pela data mesmo.")

    th = page.locator("th", has_text=data_d1).first
    if th.count() == 0:
        print(f"⚠️ Coluna com data D-1 ({data_d1}) não encontrada.")
        return None

    header_id = th.get_attribute("id")
    texto = (th.inner_text() or "").strip()

    print(f"\n✅ Coluna encontrada para D-1 ({data_d1}) | id={header_id}\n{texto}\n")
    return header_id


def _ler_coluna_por_header_id_linha_a_linha(page, header_id: str) -> list[str]:
    resultados: list[str] = []
    if not header_id:
        print("⚠️ header_id vazio, não dá para ler coluna.")
        return resultados

    # tenta achar tabela IRR correta
    tables = page.locator("table.a-IRR-table")
    try:
        count_tables = tables.count()
    except Exception:
        count_tables = 0

    print(f"debug: encontrou {count_tables} table.a-IRR-table(s).")

    table = None
    if count_tables > 0:
        for i in range(count_tables):
            t = tables.nth(i)
            try:
                has = t.locator(f"td[headers='{header_id}']").count()
            except Exception:
                has = 0
            print(f"debug: table.a-IRR-table #{i} tem {has} td[headers].")
            if has > 0:
                table = t
                break

    # fallback: qualquer <table> com td[headers=...]
    if table is None:
        generic_tables = page.locator("table")
        try:
            gt_count = generic_tables.count()
        except Exception:
            gt_count = 0
        print(f"debug: buscando em todas as <table> ({gt_count} encontradas).")
        for i in range(gt_count):
            t = generic_tables.nth(i)
            try:
                has = t.locator(f"td[headers='{header_id}']").count()
            except Exception:
                has = 0
            if has > 0:
                print(f"debug: usando table #{i} (td[headers] count={has}).")
                table = t
                break

    # se não achou tabela, varre td direto
    if table is None:
        td_nodes = page.locator(f"td[headers='{header_id}']")
        try:
            td_count = td_nodes.count()
        except Exception:
            td_count = 0
        print(f"debug: sem tabela — td[headers='{header_id}'] count={td_count}")

        for i in range(td_count):
            td = td_nodes.nth(i)
            try:
                raw = td.text_content(timeout=1500) or ""
            except Exception:
                raw = td.evaluate("el => el.textContent || ''") or ""

            texto = "\n".join([re.sub(r"[ \t]+", " ", l).strip() for l in raw.splitlines() if l.strip()])
            if texto:
                resultados.append(texto)
                print(f"--- Linha {len(resultados)} ---\n{texto}\n")

        return resultados

    # com tabela -> iterar rows do tbody
    try:
        rows = table.locator("tbody tr")
        rows_count = rows.count()
    except Exception:
        rows_count = 0

    print(f"debug: tabela escolhida tem {rows_count} linha(s) no tbody.")

    for i in range(rows_count):
        row = rows.nth(i)
        cell = row.locator(f"td[headers='{header_id}']").first
        if cell.count() == 0:
            continue

        try:
            raw = cell.text_content(timeout=1500) or ""
        except Exception:
            raw = cell.evaluate("el => el.textContent || ''") or ""

        texto = "\n".join([re.sub(r"[ \t]+", " ", l).strip() for l in raw.splitlines() if l.strip()])
        resultados.append(texto)
        print(f"--- Linha {len(resultados)} ---\n{texto}\n")

    return resultados


# =========================
# STAGE
# =========================
class Produto41Stage(Stage):
    name = "produto_41"

    def run(self, ctx) -> StageResult:
        page = ctx.page

        try:
            ctx.log("🧪 Produto 41")

            goto_distribuicao_comercial(page)

            fechar_alert_sucesso(page)
            _aguardar_refresh_tela(page)

            ctx.log("🏭 Unidade SINOP")
            selecionar_unidade(page, UNIDADE_SINOP)
            _aguardar_refresh_tela(page)

            ctx.log("🧰 Filtros")
            _click_filtros(page)

            ctx.log("📅 Data D-1")
            _set_date_d_minus_1(page)

            ctx.log("📦 Produto 41")
            _select_produto_41_lov(page)

            ctx.log("🔎 Filtrar P520")
            _click_filtrar_p520(page)
            _aguardar_refresh_tela(page)

            _ajustar_checkboxes_pos_filtrar(page)

            ctx.log("📌 Buscando coluna D-1 e lendo linhas")
            _aguardar_refresh_tela(page)

            header_id = _achar_header_id_data_d_minus_1(page)
            if not header_id:
                return StageResult(
                    name=self.name,
                    ok=False,
                    total=0,
                    details="Não foi possível encontrar a coluna D-1.",
                )

            linhas = _ler_coluna_por_header_id_linha_a_linha(page, header_id)

            ctx.log(f"✅ Linhas lidas na coluna D-1: {len(linhas)}")

            ctx.log("✅ Sucesso")
            return StageResult(
                name=self.name,
                ok=True,
                total=len(linhas),
                details="Produto 41 executado com sucesso (coluna D-1 lida).",
            )

        except Exception as e:
            ctx.log("❌ Erro:", repr(e))
            return StageResult(name=self.name, ok=False, total=0, details=str(e))