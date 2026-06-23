# bot/ui/nav.py
import re

from .apex import safe_networkidle, fechar_alert_sucesso

################# Parte do Cancelamento ###############
def _expand_tree_node_by_id(page, node_id: str, subtree_id: str, timeout_ms: int = 15000) -> None:
    """
    Expande um nó do TreeNav do APEX pelo ID (ex: t_TreeNav_3) garantindo que o subtree (ex: t_TreeNav_3_subtree) apareça.
    """
    node = page.locator(f"li#{node_id}")
    node.wait_for(state="attached", timeout=timeout_ms)

    # Se já estiver expandido (aria-expanded=true OU subtree visível), não faz nada
    subtree = page.locator(f"ul#{subtree_id}")
    try:
        if subtree.count() > 0 and subtree.first.is_visible():
            return
    except Exception:
        pass

    # Preferir clicar no toggle (setinha), é o mais confiável
    toggle = node.locator(":scope > span.a-TreeView-toggle").first
    label_span = node.locator(":scope > div.a-TreeView-content .a-TreeView-label").first

    # Tenta expandir algumas vezes (APEX às vezes ignora o 1º click)
    for _ in range(5):
        try:
            if toggle.count() > 0:
                toggle.click(timeout=3000)
            else:
                label_span.click(timeout=3000)
        except Exception:
            try:
                if toggle.count() > 0:
                    toggle.click(force=True, timeout=3000)
                else:
                    label_span.click(force=True, timeout=3000)
            except Exception:
                pass

        page.wait_for_timeout(250)

        # Confirma subtree abriu
        try:
            if subtree.count() > 0 and subtree.first.is_visible():
                return
        except Exception:
            # se o is_visible falhar, tenta esperar "visible"
            try:
                subtree.first.wait_for(state="visible", timeout=1200)
                return
            except Exception:
                pass

    # última tentativa: esperar um pouco e checar
    try:
        subtree.first.wait_for(state="visible", timeout=2000)
        return
    except Exception:
        raise RuntimeError(f"Não consegui expandir o menu {node_id} (subtree {subtree_id}).")


def goto_painel_carregamento(page) -> None:
    """
    Navega: Transporte > Carregamento > Painel
    IDs:
      Transporte   = t_TreeNav_3   (subtree t_TreeNav_3_subtree)
      Carregamento = t_TreeNav_4   (subtree t_TreeNav_4_subtree)
      Painel (link)= t_TreeNav_20  href .../painel-carregamento
    """
    fechar_alert_sucesso(page)

    # ✅ Expande Transporte
    _expand_tree_node_by_id(page, "t_TreeNav_3", "t_TreeNav_3_subtree")

    # ✅ Expande Carregamento
    _expand_tree_node_by_id(page, "t_TreeNav_4", "t_TreeNav_4_subtree")

    # ✅ Clica em Painel (preferência pelo href, mais estável que texto)
    painel = page.locator("a.a-TreeView-label[href*='/painel-carregamento']").first
    painel.wait_for(state="visible", timeout=15000)

    # Scroll + click robusto
    try:
        painel.scroll_into_view_if_needed(timeout=5000)
    except Exception:
        pass

    try:
        painel.click(timeout=5000)
    except Exception:
        painel.click(force=True, timeout=5000)

    # Aguarda navegação/assentamento
    try:
        page.wait_for_url("**/painel-carregamento**", timeout=20000)
    except Exception:
        # fallback: pelo menos esperar o DOM estabilizar
        safe_networkidle(page)
        page.wait_for_timeout(600)

    fechar_alert_sucesso(page)
################# Parte do Cancelamento ###############

def abrir_dropdown_unidades(page):
    fechar_alert_sucesso(page)
    page.locator("#B1977037496373862502").click()
    page.wait_for_selector("ul.a-IconList[role='listbox']", state="visible", timeout=20000)


def selecionar_unidade(page, texto_opcao: str):
    fechar_alert_sucesso(page)
    abrir_dropdown_unidades(page)
    page.locator("ul.a-IconList li.a-IconList-item", has_text=texto_opcao).click()
    safe_networkidle(page)
    page.wait_for_timeout(1200)


def goto_noshow(page):
    # Mantive seu padrão atual de navegação
    # page.get_by_role("treeitem", name="Transporte").click()
    page.get_by_role("treeitem", name="No-Show").click()
    safe_networkidle(page)
    page.wait_for_timeout(1200)


def goto_distribuicao_comercial(page):
    """
    Menu:
      Transporte -> Carregamento -> Distribuição Comercial

    Observação:
      existe "Descarregamento" e o Playwright pode confundir.
      Por isso usamos regex exata (^Carregamento$) e .first para evitar strict mode.
    """
    fechar_alert_sucesso(page)

    # Garante que "Transporte" está expandido (no seu print ele já está, mas deixamos robusto)
    transporte = page.get_by_role("treeitem", name=re.compile(r"^Transporte$"))
    if transporte.count() > 0:
        try:
            expanded = transporte.first.get_attribute("aria-expanded")
            if expanded == "false":
                transporte.first.click()
                page.wait_for_timeout(500)
        except Exception:
            pass

    # ✅ "Carregamento" EXATO (não pega "Descarregamento")
    carregamento = page.get_by_role("treeitem", name=re.compile(r"^Carregamento$"))
    carregamento.first.wait_for(state="visible", timeout=20000)

    # Expande se estiver fechado
    try:
        expanded = carregamento.first.get_attribute("aria-expanded")
        if expanded == "false" or expanded is None:
            carregamento.first.click()
            page.wait_for_timeout(600)
    except Exception:
        carregamento.first.click()
        page.wait_for_timeout(600)

    # ✅ Agora aparece "Distribuição Comercial"
    distribuicao = page.get_by_role("treeitem", name=re.compile(r"^Distribuição Comercial$"))
    distribuicao.first.wait_for(state="visible", timeout=20000)
    distribuicao.first.click()

    safe_networkidle(page)
    page.wait_for_timeout(1200)


def goto_consulta_produto(page):
    """
    Se você quiser manter um alias para a etapa do Produto 41,
    pode apontar para a mesma navegação.
    """
    goto_distribuicao_comercial(page)