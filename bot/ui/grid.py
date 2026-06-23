import re
import time


def unidade_codigo(unidade_label: str) -> str:
    m = re.match(r"\s*([0-9]+(?:\.[0-9]+)+)\s*-", unidade_label)
    return m.group(1) if m else unidade_label.strip()


def existe_nenhum_dado(page) -> bool:
    return page.locator('div.a-GV-altMessage-icon[aria-label="Nenhum dado encontrado"]').count() > 0


def tem_linhas_no_grid(page) -> bool:
    return page.locator("tbody tr[role='row']").count() > 0


def achar_link_cancelar_visivel(page, visible_scan_limit: int):
    links = page.locator("a[title='Cancelar agendamento']")
    if links.count() == 0:
        return None

    max_scan = min(links.count(), visible_scan_limit)
    for i in range(max_scan):
        li = links.nth(i)
        try:
            if li.is_visible():
                return li
        except Exception:
            pass
    return None


def tem_cancelar_visivel(page, visible_scan_limit: int) -> bool:
    return achar_link_cancelar_visivel(page, visible_scan_limit) is not None


def esperar_grid_responder(page, fechar_alert_sucesso_fn, safe_networkidle_fn, *,
                          grid_timeout_s: int, poll_ms: int, visible_scan_limit: int) -> str:
    """
    Retorna: NENHUM_DADO | TEM_CANCELAR_VISIVEL | TEM_LINHAS | TIMEOUT
    """
    deadline = time.time() + grid_timeout_s

    fechar_alert_sucesso_fn(page)
    safe_networkidle_fn(page)
    page.wait_for_timeout(600)

    while time.time() < deadline:
        fechar_alert_sucesso_fn(page)

        if existe_nenhum_dado(page):
            return "NENHUM_DADO"

        if tem_cancelar_visivel(page, visible_scan_limit):
            return "TEM_CANCELAR_VISIVEL"

        if tem_linhas_no_grid(page):
            page.wait_for_timeout(700)
            if tem_cancelar_visivel(page, visible_scan_limit):
                return "TEM_CANCELAR_VISIVEL"
            return "TEM_LINHAS"

        page.wait_for_timeout(poll_ms)

    return "TIMEOUT"