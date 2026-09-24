"""Accumulated backtest metrics."""

from __future__ import annotations

from schemas import BacktestMetrics


class MetricsAccumulator:
    def __init__(self):
        self.metrics = BacktestMetrics()
        self._admin_expense_rate = 0.05

    def record_issued(self, premium_brl: float, pure_premium_brl: float) -> None:
        self.metrics.policies_issued += 1
        self.metrics.total_premium_brl += premium_brl
        self.metrics.expected_pure_premium_brl += pure_premium_brl
        self._refresh()

    def record_rejected(self) -> None:
        self.metrics.policies_rejected += 1

    def record_claim(self, paid_brl: float) -> None:
        if paid_brl > 0:
            self.metrics.claims_with_payout += 1
            self.metrics.total_claims_brl += paid_brl
        else:
            self.metrics.claims_without_payout += 1
        self._refresh()

    def _refresh(self) -> None:
        if self.metrics.total_premium_brl > 0:
            self.metrics.loss_ratio = self.metrics.total_claims_brl / self.metrics.total_premium_brl
            admin = self.metrics.total_premium_brl * self._admin_expense_rate
            self.metrics.combined_ratio = (self.metrics.total_claims_brl + admin) / self.metrics.total_premium_brl
        if self.metrics.expected_pure_premium_brl > 0:
            self.metrics.premium_vs_pure_ratio = (
                self.metrics.total_premium_brl / self.metrics.expected_pure_premium_brl
            )

    def snapshot(self) -> BacktestMetrics:
        return self.metrics.model_copy(deep=True)
