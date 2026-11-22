from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MetricPair:
    label: str
    before: float | None
    after: float | None
    unit: str
    lower_is_better: bool = True

    @property
    def before_text(self) -> str:
        return self._fmt(self.before)

    @property
    def after_text(self) -> str:
        return self._fmt(self.after)

    def _fmt(self, value: float | None) -> str:
        if value is None:
            return "—"
        if self.unit == "FPS":
            return f"{value:.0f}"
        if self.unit == "%":
            return f"{value:.0f}%"
        if self.unit == "ms":
            return f"{value:.0f} ms"
        return f"{value:.1f}{self.unit}"

    @property
    def delta_text(self) -> str:
        if self.before is None or self.after is None:
            return "—"
        delta = self.after - self.before
        if abs(delta) < 0.05:
            return "持平"
        improved = delta < 0 if self.lower_is_better else delta > 0
        sign = "+" if delta > 0 else ""
        unit = self.unit if self.unit != "FPS" else ""
        if self.unit == "ms":
            body = f"{sign}{delta:.0f} ms"
        elif self.unit == "%":
            body = f"{sign}{delta:.0f}%"
        elif self.unit == "FPS":
            body = f"{sign}{delta:.0f}"
        else:
            body = f"{sign}{delta:.1f}{unit}"
        return f"{body} · {'變好' if improved else '變差'}"


@dataclass
class SessionCompare:
    ping_ms: MetricPair
    cpu_percent: MetricPair
    fps: MetricPair
    note: str = ""

    @classmethod
    def empty(cls) -> SessionCompare:
        return cls(
            ping_ms=MetricPair("延遲", None, None, "ms", True),
            cpu_percent=MetricPair("CPU", None, None, "%", True),
            fps=MetricPair("FPS", None, None, "FPS", False),
            note="加速前後會顯示對照",
        )
