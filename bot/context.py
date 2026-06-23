from dataclasses import dataclass, field
from typing import Any
from openpyxl import Workbook
from datetime import datetime


@dataclass
class BotContext:
    page: Any
    wb: Workbook
    ws: Any
    xlsx_path: str
    jsonl_path: str
    config: Any

    # histórico noshow
    historico_wb: Workbook | None = None
    historico_path: str | None = None

    # ✅ NOVO: caminho do log
    log_path: str | None = None

    state: dict[str, Any] = field(default_factory=dict)

    def log(self, *args):
        msg = " ".join(str(a) for a in args)

        # print no console
        print(msg)

        # salvar em arquivo
        if self.log_path:
            try:
                with open(self.log_path, "a", encoding="utf-8") as f:
                    f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
            except Exception:
                pass