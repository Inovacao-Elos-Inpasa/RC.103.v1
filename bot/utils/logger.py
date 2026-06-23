import logging
from pathlib import Path
from datetime import datetime


def setup_logger():
    # 📁 pasta de logs
    log_dir = Path("relatorios/logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    # 🕒 nome do arquivo
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file = log_dir / f"execucao_{timestamp}.log"

    # ⚙️ configuração
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler()  # continua aparecendo no console
        ]
    )

    return logging.getLogger()