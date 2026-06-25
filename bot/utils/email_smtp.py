import smtplib
from email.message import EmailMessage
from datetime import datetime
import os
from pathlib import Path


XLSX_MIME = "vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def enviar_email_smtp(
    arquivos: list[str],
    tem_noshow: bool = True,
    tem_cancelamento: bool = True
):
    hoje = datetime.now().strftime("%d/%m/%Y")

    smtp_user = os.environ.get("SMTP_USER", "").strip()
    smtp_pass = os.environ.get("SMTP_PASS", "").strip()
    smtp_server = os.environ.get("SMTP_HOST", "smtp.office365.com").strip()
    smtp_port = int(os.environ.get("SMTP_PORT", 587))


    # ✅ vários destinatários
    destinatarios = [
        "daniel@zixbe.com.br",
        "jessica.sampaio@inpasa.com.br",
        "luciana.holtman@inpasa.com.br",
        "analista.ddgs@inpasa.com.br",
        "franklin.guisso@inpasa.com.br",
        "izadora.feitosa@inpasa.com.br",
        "washington.silva@inpasa.com.br",
        "edberg.silva@inpasa.com.br",
        "luciane.rosa@inpasa.com.br"
    ]


    assunto = f"Planilha Cancelamento ({hoje})"

    # ============================================================
    # 🧠 MENSAGEM DINÂMICA
    # ============================================================

    mensagens = []

    if not tem_noshow:
        mensagens.append("Não houve registros de No-Show no período.")

    if not tem_cancelamento:
        mensagens.append("Não houve registros de cancelamentos no período.")

    if not mensagens:
        resumo = "Todos os relatórios possuem registros."
    else:
        resumo = "\n".join(mensagens)

    # ============================================================

    corpo = f"""Bom dia,

Segue em anexo os relatórios do dia.

{resumo}

Lembrando que essas planilhas abrangem os produtos 41, 154 e 159.

Atenciosamente,
"""

    msg = EmailMessage()
    msg["Subject"] = assunto
    msg["From"] = smtp_user
    msg["To"] = ", ".join(destinatarios)
    msg.set_content(corpo)

    # ============================================================
    # 📎 ANEXOS (IGNORA VAZIOS AUTOMATICAMENTE)
    # ============================================================

    for arquivo in arquivos:
        if not arquivo:
            continue

        p = Path(arquivo)

        if not p.exists():
            continue

        # ⚠️ ignora arquivo vazio (0 bytes)
        if p.stat().st_size == 0:
            continue

        with p.open("rb") as f:
            file_data = f.read()

        if p.suffix.lower() == ".xlsx":
            msg.add_attachment(
                file_data,
                maintype="application",
                subtype=XLSX_MIME,
                filename=p.name,
            )
        else:
            msg.add_attachment(
                file_data,
                maintype="application",
                subtype="octet-stream",
                filename=p.name,
            )

    # ============================================================
    # 📤 ENVIO
    # ============================================================

    with smtplib.SMTP(smtp_server, smtp_port, timeout=60) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)
