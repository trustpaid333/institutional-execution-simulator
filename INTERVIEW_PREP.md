# Interview Preparation — Institutional Execution Simulator

These are **illustrative practice questions**, not leaked or verified questions from Jane Street or Optiver.

## Explain the project in 45–60 seconds (English)

> I built an educational Python simulator to compare three ways of executing a large institutional order: immediate execution, TWAP, and participation of volume. I created synthetic market-price and liquidity scenarios, modeled a simplified spread and impact cost, and calculated implementation shortfall and fill rates. I used the same market paths for each strategy so the comparisons were fair. Under my baseline assumptions, splitting the order reduced average modeled execution cost, but increased exposure to price movements. The main limitation is that the simulator uses synthetic liquidity rather than real order-book data.

Practice saying this *in your own words*, without memorizing it line for line.

## Questions to practice

**1. What is the difference between spread cost and market impact?**

- Spread cost: crossing the bid-ask spread to trade immediately.
- Modeled impact: additional cost from sending an order that is large relative to available liquidity.
- In this particular toy model, impact does **not** change the next market midprice.

**2. Why not always use TWAP if its mean shortfall was lower?**

- The mean alone hides substantial timing risk and a wide distribution.
- Results depend on the simulated environment and assumed impact.
- A client may require immediate completion or have a firm deadline.

**3. What is implementation shortfall?**

The cost relative to a decision-time benchmark, here the arrival midprice. This model adds fees and a final-price opportunity-cost adjustment for unfinished shares.

**4. Why use the same paths across strategies?**

To compare how each strategy performs in the *same* price and liquidity scenario, rather than mixing strategy effects with unrelated random market moves.

**5. What's the drawback of POV?**

It adjusts execution size to contemporaneous activity, but may not complete the order before the deadline. Also, bucket-level realized volume assumes idealized continuous participation; a production version requires actual observed prints and orders.

**6. Could this backtest real QQQ execution performance?**

No. The model uses synthetic data, assumed fills and an uncalibrated impact formula. It lacks real intraday trades, quotes, queue placement and adverse selection.

**7. What would you improve first?**

Choose and defend one: calibrate to real intraday data; incorporate depth-sensitive multi-level fills; or add a causal real-time POV execution policy.

**8. What happens to a buy order if midprice rises while you wait?**

Timing cost generally increases. A faster completion can protect against that move, at the expense of potentially larger immediate liquidity costs.

**9. Why can shortfall be negative?**

The order can benefit from favorable market moves relative to the arrival benchmark. Negative cost on one simulation is not a guarantee for the next.

**10. How does buy vs. sell change the analysis?**

The sign of the midprice deviation and opportunity-cost terms flips. Buying above the benchmark is unfavorable; selling below it is unfavorable.

## One calculation worth being able to do mentally

You buy 10,000 shares. The arrival midprice is $100.00. You execute all shares at $100.06 and pay $20 in fees.

- Price difference per share = $0.06
- Gross shortfall = 10,000 × $0.06 = $600
- Total shortfall = $620
- Benchmark notional = $1,000,000
- Shortfall in bps = 10,000 × 620 / 1,000,000 = **6.2 bps**

Be able to explain the benchmark and the bps conversion, not just the result.