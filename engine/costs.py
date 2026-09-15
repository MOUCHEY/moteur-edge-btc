"""
Modele de couts. Fixe par le protocole, non negociable par experience.

AVERTISSEMENT — ces valeurs sont des HYPOTHESES, pas des mesures. Elles n'ont
pas ete tirees des releves de courtier de Jeunathan. Tant que ce n'est pas fait,
tout resultat de ce depot doit etre lu comme conditionnel a ces chiffres.
Voir docs/COUTS.md.
"""
from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class CostModel:
    """Couts en points de base (1 bp = 0,01 %), exprimes ALLER-RETOUR."""
    spread_bps: float = 4.0      # BTCUSD CFD retail typique, a remplacer par mesure
    slippage_bps: float = 2.0    # execution au marche, hypothese conservatrice
    commission_bps: float = 0.0  # la plupart des CFD crypto n'en facturent pas
    funding_bps_per_day: float = 2.7  # ~10 %/an, cout de portage d'une position

    def __post_init__(self) -> None:
        for name in ("spread_bps", "slippage_bps", "commission_bps", "funding_bps_per_day"):
            value = getattr(self, name)
            if isinstance(value, bool) or not math.isfinite(value) or value < 0:
                raise ValueError(f"cout {name} : valeur finie positive ou nulle requise")

    def round_trip(self) -> float:
        return self.spread_bps + self.slippage_bps + self.commission_bps

    def holding(self, bars: float, bar_seconds: int) -> float:
        """Portage lineaire hypothetique, y compris les fractions de jour."""
        if (not math.isfinite(bars) or bars < 0 or not math.isfinite(bar_seconds)
                or bar_seconds <= 0):
            raise ValueError("duree de portage invalide")
        days = bars * bar_seconds / 86400.0
        return days * self.funding_bps_per_day

    def total(self, bars_held: float, bar_seconds: int) -> float:
        return self.round_trip() + self.holding(bars_held, bar_seconds)

    def scaled(self, factor: float) -> "CostModel":
        if isinstance(factor, bool) or not math.isfinite(factor) or factor < 0:
            raise ValueError("facteur de cout fini positif ou nul requis")
        return CostModel(self.spread_bps * factor, self.slippage_bps * factor,
                         self.commission_bps * factor, self.funding_bps_per_day * factor)


DEFAULT = CostModel()
