"""Educational execution-cost simulator. All prices and volumes are SYNTHETIC.

The three strategies use the same simulated market path within each scenario:
- Immediate: aggressively fill the entire order at the first available quote.
- TWAP: spread integer-share fills across time buckets.
- POV: cap participation at a fixed fraction of each bucket's market volume.

This is deliberately not a full limit order book or a real QQQ backtest.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


STRATEGIES = ("Immediate", "TWAP", "POV")


@dataclass(frozen=True)
class Config:
    side: str = "buy"
    shares: int = 100_000
    initial_mid: float = 450.0
    buckets: int = 20
    volatility_bps_per_bucket: float = 12.0
    drift_bps_per_bucket: float = 0.0
    typical_spread_bps: float = 0.8
    typical_market_volume: int = 60_000
    typical_book_depth: int = 12_000
    impact_coefficient_bps: float = 1.8
    participation_rate: float = 0.10
    fee_per_share: float = 0.002
    seed: int = 42

    def __post_init__(self) -> None:
        if self.side not in {"buy", "sell"}:
            raise ValueError("side must be 'buy' or 'sell'")
        if self.shares <= 0 or self.buckets <= 0:
            raise ValueError("shares and buckets must be positive")
        if self.initial_mid <= 0 or self.typical_book_depth <= 0 or self.typical_market_volume <= 0:
            raise ValueError("initial_mid, typical_book_depth, and typical_market_volume must be positive")
        if not 0 < self.participation_rate <= 1:
            raise ValueError("participation_rate must be in (0, 1]")
        if any(value < 0 for value in (
            self.volatility_bps_per_bucket, self.typical_spread_bps,
            self.impact_coefficient_bps, self.fee_per_share,
        )):
            raise ValueError("volatility, spread, impact and fees cannot be negative")


@dataclass(frozen=True)
class MarketPath:
    mid: np.ndarray
    spread_bps: np.ndarray
    market_volume: np.ndarray
    book_depth: np.ndarray


def generate_market_path(cfg: Config, rng: np.random.Generator) -> MarketPath:
    """Simulate prices, spread and liquidity for one hypothetical trading session."""
    log_returns = rng.normal(
        loc=cfg.drift_bps_per_bucket * 1e-4,
        scale=cfg.volatility_bps_per_bucket * 1e-4,
        size=cfg.buckets - 1,
    )
    mid = cfg.initial_mid * np.exp(np.r_[0.0, np.cumsum(log_returns)])

    # Lognormal factor with approximately unit arithmetic mean.
    volume_factor = rng.lognormal(mean=-0.5 * 0.45**2, sigma=0.45, size=cfg.buckets)
    spread_factor = rng.lognormal(mean=-0.5 * 0.25**2, sigma=0.25, size=cfg.buckets)
    market_volume = np.maximum(1, np.rint(cfg.typical_market_volume * volume_factor)).astype(int)
    book_depth = cfg.typical_book_depth * np.power(volume_factor, 0.35)
    spread_bps = cfg.typical_spread_bps * spread_factor
    return MarketPath(mid=mid, spread_bps=spread_bps, market_volume=market_volume, book_depth=book_depth)


def child_order_sizes(strategy: str, cfg: Config, path: MarketPath) -> np.ndarray:
    """Integer shares per bucket; POV can leave part of an order unfilled."""
    sizes = np.zeros(cfg.buckets, dtype=int)
    if strategy == "Immediate":
        sizes[0] = cfg.shares
    elif strategy == "TWAP":
        base, extra = divmod(cfg.shares, cfg.buckets)
        sizes[:] = base
        sizes[:extra] += 1
    elif strategy == "POV":
        remaining = cfg.shares
        for t in range(cfg.buckets):
            available = int(np.floor(cfg.participation_rate * path.market_volume[t]))
            sizes[t] = min(available, remaining)
            remaining -= sizes[t]
    else:
        raise ValueError(f"Unknown strategy: {strategy}")
    return sizes


def execute_order(strategy: str, cfg: Config, path: MarketPath) -> tuple[dict, pd.DataFrame]:
    """Return execution summary and per-bucket fills for one shared market path.

    Decomposition in dollars, with side=+1 for buy and -1 for sell:
    implementation shortfall = timing + spread + impact + fees + opportunity.
    A negative shortfall is possible if prices move favorably.
    """
    side_sign = 1 if cfg.side == "buy" else -1
    q = child_order_sizes(strategy, cfg, path)
    arrival_mid = float(path.mid[0])
    half_spread = path.mid * path.spread_bps * 1e-4 / 2
    # Exogenous impact is a simplified child-order penalty, not permanent price impact.
    impact = path.mid * cfg.impact_coefficient_bps * 1e-4 * np.sqrt(q / path.book_depth)
    fill_price = path.mid + side_sign * (half_spread + impact)

    executed = int(q.sum())
    unfilled = cfg.shares - executed
    if unfilled < 0:
        raise AssertionError("Overfill is not allowed")
    notional = float(np.dot(q, fill_price))
    fees = cfg.fee_per_share * executed
    timing_cost = float(side_sign * np.dot(q, path.mid - arrival_mid))
    spread_cost = float(np.dot(q, half_spread))
    impact_cost = float(np.dot(q, impact))
    # A shortfall for an unfilled order is marked at the final simulated mid.
    opportunity_cost = float(side_sign * unfilled * (path.mid[-1] - arrival_mid))
    total_shortfall = timing_cost + spread_cost + impact_cost + fees + opportunity_cost
    direct_shortfall = side_sign * (notional - arrival_mid * executed) + fees + opportunity_cost
    if not np.isclose(total_shortfall, direct_shortfall, atol=1e-5):
        raise AssertionError("Cost decomposition mismatch")

    metrics = {
        "strategy": strategy,
        "side": cfg.side,
        "order_shares": cfg.shares,
        "filled_shares": executed,
        "unfilled_shares": unfilled,
        "fill_pct": 100 * executed / cfg.shares,
        "arrival_mid": arrival_mid,
        "terminal_mid": float(path.mid[-1]),
        "execution_vwap": notional / executed if executed else float("nan"),
        "timing_cost_usd": timing_cost,
        "spread_cost_usd": spread_cost,
        "impact_cost_usd": impact_cost,
        "fees_usd": fees,
        "opportunity_cost_usd": opportunity_cost,
        "implementation_shortfall_usd": total_shortfall,
        "implementation_shortfall_bps": 10_000 * total_shortfall / (cfg.shares * arrival_mid),
    }
    executions = pd.DataFrame({
        "bucket": np.arange(1, cfg.buckets + 1),
        "child_shares": q,
        "cumulative_filled": np.cumsum(q),
        "execution_price": np.where(q > 0, fill_price, np.nan),
    })
    return metrics, executions


def summarize_results(results: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for strategy in STRATEGIES:
        df = results[results["strategy"] == strategy]
        shortfall = df["implementation_shortfall_bps"]
        rows.append({
            "strategy": strategy,
            "scenarios": len(df),
            "mean_shortfall_bps": shortfall.mean(),
            "median_shortfall_bps": shortfall.median(),
            "p10_shortfall_bps": shortfall.quantile(0.10),
            "p90_shortfall_bps": shortfall.quantile(0.90),
            "std_shortfall_bps": shortfall.std(ddof=0),
            "mean_fill_pct": df["fill_pct"].mean(),
            "incomplete_rate_pct": 100 * (df["unfilled_shares"] > 0).mean(),
        })
    return pd.DataFrame(rows)


def plot_shortfalls(results: pd.DataFrame, out_path: Path) -> None:
    data = [results.loc[results["strategy"] == s, "implementation_shortfall_bps"].to_numpy() for s in STRATEGIES]
    fig, ax = plt.subplots(figsize=(8.5, 5))
    ax.boxplot(data, tick_labels=STRATEGIES, showfliers=False)
    ax.axhline(0, linestyle="--", linewidth=1, color="gray")
    ax.set_title("Simulated implementation shortfall (same paths per strategy)")
    ax.set_ylabel("Implementation shortfall (basis points)")
    ax.set_xlabel("Execution strategy")
    ax.grid(alpha=0.2, axis="y")
    fig.tight_layout()
    fig.savefig(out_path, dpi=160)
    plt.close(fig)


def plot_example_path(path: MarketPath, executions: dict[str, pd.DataFrame], out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 5.5))
    buckets = np.arange(1, len(path.mid) + 1)
    ax.plot(buckets, path.mid, linewidth=2, label="Synthetic midprice", color="black")
    for name, trades in executions.items():
        bought = trades[trades["child_shares"] > 0]
        ax.scatter(bought["bucket"], bought["execution_price"], s=32, alpha=0.7, label=f"{name} fills")
    ax.set_title("One synthetic price path and aggressive execution prices")
    ax.set_xlabel("Time bucket")
    ax.set_ylabel("Synthetic share price ($)")
    ax.grid(alpha=0.2)
    ax.legend(fontsize=9)
    fig.tight_layout()
    fig.savefig(out_path, dpi=160)
    plt.close(fig)


def run_simulation(cfg: Config, scenarios: int, output_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    if scenarios <= 0:
        raise ValueError("scenarios must be positive")
    output_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(cfg.seed)
    result_rows = []
    example_path = None
    example_executions = {}

    for scenario in range(1, scenarios + 1):
        path = generate_market_path(cfg, rng)
        for strategy in STRATEGIES:
            metrics, trades = execute_order(strategy, cfg, path)
            result_rows.append({"scenario": scenario, **metrics})
            if scenario == 1:
                example_executions[strategy] = trades
        if scenario == 1:
            example_path = path

    results = pd.DataFrame(result_rows)
    summary = summarize_results(results)
    results.to_csv(output_dir / "scenario_results.csv", index=False, float_format="%.8f")
    summary.to_csv(output_dir / "summary.csv", index=False, float_format="%.8f")

    assert example_path is not None
    sample = pd.DataFrame({
        "bucket": np.arange(1, cfg.buckets + 1),
        "midprice": example_path.mid,
        "spread_bps": example_path.spread_bps,
        "market_volume": example_path.market_volume,
        "book_depth_shares": example_path.book_depth,
    })
    for strategy, trades in example_executions.items():
        for name in ("child_shares", "cumulative_filled", "execution_price"):
            sample[f"{strategy.lower()}_{name}"] = trades[name]
    sample.to_csv(output_dir / "example_path.csv", index=False, float_format="%.8f")
    plot_shortfalls(results, output_dir / "shortfall_boxplot.png")
    plot_example_path(example_path, example_executions, output_dir / "example_execution.png")
    return results, summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Synthetic execution cost simulator (educational)")
    parser.add_argument("--scenarios", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--side", choices=["buy", "sell"], default="buy")
    parser.add_argument("--shares", type=int, default=100_000)
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    args = parser.parse_args()
    cfg = Config(side=args.side, shares=args.shares, seed=args.seed)
    _, summary = run_simulation(cfg, args.scenarios, args.output_dir)
    print("\nSYNTHETIC execution results — not a real-market backtest")
    print(f"Order: {cfg.side.upper()} {cfg.shares:,} shares | scenarios: {args.scenarios:,} | seed: {cfg.seed}")
    print(summary.round(3).to_string(index=False))
    print(f"\nSaved CSV files and charts to: {args.output_dir.resolve()}")


if __name__ == "__main__":
    main()