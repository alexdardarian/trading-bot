from dataclasses import dataclass

# Trigger: portfolio drops 20% from all-time peak → scale to 50% equities
# Restore: portfolio recovers to within 10% of peak → back to 100% equities
# Hysteresis band prevents rapid toggling during choppy recoveries.
BRAKE_TRIGGER  = -0.20
BRAKE_RESTORE  = -0.10
BRAKE_FRACTION =  0.50   # fraction BY WHICH to reduce equity exposure when active
                          # equity_fraction = 1 - BRAKE_FRACTION (e.g. 0.50 → keep 50%)


@dataclass
class BrakeState:
    active: bool  = False
    peak:   float = 0.0


def update(state: BrakeState, value: float) -> BrakeState:
    """
    Pure state machine — returns a new BrakeState, never mutates the input.

    Peak tracks the all-time high-watermark across the full simulation,
    not just since the brake was activated.  This prevents the brake from
    inadvertently deactivating during a dead-cat bounce that doesn't recover
    the true peak.

    Intra-month drawdowns do NOT trigger intra-month rebalances.  The brake
    state changes immediately, but the equity-fraction reduction only takes
    effect on the next scheduled monthly rebalance.  This avoids forced
    liquidation at the worst possible time during a market panic.
    """
    peak = max(state.peak, value)
    dd   = (value - peak) / peak if peak > 0 else 0.0

    if not state.active and dd <= BRAKE_TRIGGER:
        return BrakeState(active=True,  peak=peak)
    if state.active  and dd >= BRAKE_RESTORE:
        return BrakeState(active=False, peak=peak)
    return BrakeState(active=state.active, peak=peak)


def equity_fraction(state: BrakeState) -> float:
    """Returns the fraction of portfolio value to keep in equities."""
    return 1.0 - BRAKE_FRACTION if state.active else 1.0
