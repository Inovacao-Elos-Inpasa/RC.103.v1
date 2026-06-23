def safe_networkidle(page, timeout=20000):
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except Exception:
        pass


def fechar_alert_sucesso(page):
    try:
        alert = page.locator("#t_Alert_Success")
        if alert.count() == 0:
            return

        if not alert.is_visible():
            return

        btn = alert.locator("button.t-Button--closeAlert")
        if btn.count() > 0:
            try:
                btn.first.click(timeout=3000)
                page.wait_for_timeout(300)
            except Exception:
                try:
                    btn.first.click(force=True, timeout=3000)
                    page.wait_for_timeout(300)
                except Exception:
                    pass

        try:
            alert.wait_for(state="hidden", timeout=4000)
        except Exception:
            pass
    except Exception:
        pass


def clicar_sim_confirmacao_apex(page) -> bool:
    sim = page.locator("button.js-confirmBtn.ui-button--hot", has_text="Sim")
    if sim.count() == 0:
        return False
    try:
        sim.first.click(timeout=7000)
        page.wait_for_timeout(500)
        return True
    except Exception:
        try:
            sim.first.click(force=True, timeout=7000)
            page.wait_for_timeout(500)
            return True
        except Exception:
            return False


def tentar_confirmacoes_genericas(page):
    for txt in ["Sim", "OK", "Confirmar", "Yes"]:
        btn = page.get_by_role("button", name=txt)
        if btn.count() > 0:
            try:
                btn.first.click(timeout=2500)
                page.wait_for_timeout(400)
            except Exception:
                pass