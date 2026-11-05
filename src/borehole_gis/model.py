from dataclasses import dataclass, field


@dataclass
class Issue:
    severity: str
    code: str
    group: str
    row: int
    hole_id: str
    message: str


@dataclass
class Hole:
    id: str
    x: float
    y: float
    final_depth: float
    row: int


@dataclass
class Interval:
    hole_id: str
    top: float
    base: float
    description: str
    row: int


@dataclass
class SPT:
    hole_id: str
    depth: float
    n: float | None
    row: int
    remark: str = ""


@dataclass
class Dataset:
    crs: str
    holes: list[Hole] = field(default_factory=list)
    intervals: list[Interval] = field(default_factory=list)
    spts: list[SPT] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)

    def issue(self, code, group, row, hole_id, message, severity="error"):
        self.issues.append(Issue(severity, code, group, row, hole_id, message))

    @property
    def errors(self):
        return sum(i.severity == "error" for i in self.issues)
