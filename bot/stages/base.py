from dataclasses import dataclass


@dataclass
class StageResult:
    name: str
    ok: bool
    total: int = 0
    details: str = ""


class Stage:
    name = "base"

    def run(self, ctx) -> StageResult:
        raise NotImplementedError