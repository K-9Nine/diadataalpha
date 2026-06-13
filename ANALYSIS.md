# DIA Data — Investment Analysis (for scrutiny)

> **Purpose:** answer "Is DIA a buy at the current price, and what is fair value?"
> in a way that can be **challenged**. Every figure has a source and an `as_of`.
> **Not financial advice** — research signals only. Several inputs are proxies or
> manual entries, flagged as such.
>
> **Snapshot date:** 2026-06-13. **Reproduce:** `python -m dia_alpha_monitor run && python -m dia_alpha_monitor report`.

---

## 1. The data (with sources)

| Metric | Value | Source | Confidence |
|---|---|---|---|
| Price | $0.1223 | CoinGecko `dia-data` | High (cross-checked) |
| DIA self-reported price (signed) | $0.1221 (+0.1% vs CG) | DIA API `assetQuotation` | High — two independent sources agree |
| Market cap | $14.65M | CoinGecko | High |
| FDV | $20.66M | CoinGecko | High |
| Circulating / total supply | 119.68M / 168.82M | CoinGecko | High |
| **Official DIA oracle TVS** | **$148.23M** | **DefiLlama `/oracles/DIA`** | Med — single manual reading |
| TVS concentration | Zest ~48%, Rezerve, FortiFi | DefiLlama | Med |
| Lasernet throughput (daily tx) | 313,152 · **+53% 7d / +45% 30d** | explorer.diadata.org (Blockscout) | High — on-chain, 31d history |
| DIA feed coverage | 5,859 crypto feeds, 102 chains, 83 active scrapers | DIA API | High |
| DIA RWA assets (reported) | 20,000+ | diadata.org (manual) | Low — DIA's own headline, not independently counted |
| Staking | 4.4M DIA, 11 feeders, 12.56% APY (→5-6% Jul 1) | DIA blog (manual, 2026-06-05) | Med |
| Mainnet grants/integrations | 8 (100% to-mainnet), 1 new in 30d | manual, DIA-sourced | Med |
| Price momentum | 1d -1.6%, 7d -4.0%, **30d -38.5%** | CoinGecko | High |
| Alpha score (tool) | 55.7 / 100 | computed | — |

**Competitor market caps:** Chainlink $5.73B · Pyth $294.73M · RedStone $39.52M · API3 $36.35M · Chronicle (no liquid token).
**DIA vs peers:** 0.26% of Chainlink · ~5.0% of Pyth · ~37% of RedStone · ~40% of API3.

---

## 2. The single most important correction

The tool originally reported a **"DIA-linked TVL proxy" of $11.30B gross / $2.31B
confidence-weighted.** That is **NOT** what DIA secures. It is the *whole* TVL of
every protocol that uses DIA *somewhere* (e.g. Morpho's entire ~$10B), which is an
**upper bound on reach**, not secured value.

DefiLlama's official per-oracle TVS — which counts only the markets/pools DIA
actually secures — is **$148.23M**. So:

- The reach proxy **overstates DIA's real secured value by ~76× (gross) / ~16× (weighted)**.
- The report has been **recalibrated** (§3) to lead with the $148.23M official TVS
  and label the proxy explicitly as reach, not secured value.

**Implication:** DIA's real on-chain footprint is **modest (~$148M secured)** — small
versus Chainlink (tens of $B). Any bull case must rest on *growth*, not current scale.

---

## 3. Is it a buy? (verdict: speculative accumulate)

The setup is **asymmetric but unproven**:

**For (constructive, evidence-backed):**
- **Cheap vs peers:** $14.65M mcap = 0.37–0.40× of API3/RedStone despite arguably broader product (RWA, Lasernet rollup, VRF, 20-chain grants).
- **Cheap vs its own secured value:** mcap/TVS = **0.10×**.
- **Usage is growing:** Lasernet throughput **+45% in 30 days** — the first hard, trustless evidence the oracle is being used *more*, not just integrated.
- **Real adoption:** $148M TVS across real protocols (Zest, Rezerve, FortiFi); 8 mainnet integrations; active RWA shipping (hemiBTC, Hermetica, Parallel, River).
- **Token utility transitioning:** Lasernet gas + staking (4.4M staked, rising).

**Against (risks / unproven):**
- **Momentum is negative:** −38.5% over 30d — catching a falling knife.
- **Small absolute scale:** $148M TVS is tiny in oracle terms.
- **Monetisation unproven:** no public fee/revenue figure ties usage → token value. TVS ≠ revenue.
- **Concentration risk:** ~48% of TVS is a single protocol (Zest).
- **The proxy lesson:** headline "adoption" numbers can be 16–76× too generous; treat all reach/announcement metrics with suspicion.

**Verdict:** at $0.12 the risk/reward is **favourably skewed for a small, thesis-driven
position** — limited fundamental downside (real, growing usage; deep discount), multi-× upside
if usage converts to fees. It is **not** a high-conviction buy. Best expressed as a
**sized, averaged-in accumulate**, contingent on the usage→fees link being proven.

---

## 4. Fair value range (with the math, so it can be challenged)

Implied price = target market cap ÷ 119.68M circulating supply.

| Method | Anchor | Implied mcap | **Implied price** | vs $0.1223 | Notes |
|---|---|---|---|---|---|
| **Peer parity** (most defensible) | = API3/RedStone ($36–40M) | $36–40M | **$0.30–0.33** | 2.5–2.7× | DIA's nearest liquid peers; comparable/broader product |
| **TVS multiple** (cross-check) | 0.3–0.5× of $148M TVS | $44–74M | **$0.37–0.62** | 3–5× | Heuristic — TVS is not revenue |
| **Pyth fraction** | 10% of Pyth | $29.5M | $0.25 | 2.0× | Modest |
| **Chainlink fraction** (bull) | 1–2.5% of Chainlink | $57–143M | **$0.48–1.20** | 3.9–9.8× | Requires real oracle-share capture |

**Fair-value range: ~$0.30–0.62 (base, ≈2.5–5×)**, anchored to peer-parity and a
conservative TVS multiple. **Bull extension to ~$1.20 (≈10×)** if DIA captures
1–2.5% of Chainlink-scale share as the RWA/usage thesis pays off. **Downside floor
~$0.08–0.12** if the thesis stalls (real assets/usage limit how far it falls, but a
governance-only token with no fee capture could stay here).

---

## 5. Explicit assumptions (challenge these)

1. **Comparability:** DIA ≈ API3/RedStone in substance. *If DIA is structurally weaker, the floor/base are too high.*
2. **Supply:** FV uses **circulating** supply (119.68M). Total is 168.82M (~41% more) — emissions/unlocks would dilute; FDV-based targets are ~29% lower.
3. **TVS multiple is a heuristic**, not a revenue multiple. Oracles earn fees, not a % of TVS. *Treat the TVS-multiple row as weakest.*
4. **The 500k DIA position** in the tool is the user's stated holding (@ ~$0.18) — irrelevant to FV, used only for PnL scenarios.
5. **Lasernet throughput ≈ oracle usage** — true because Lasernet is a dedicated oracle rollup, but a tx-count spike could be non-economic (test/spam); needs sustained confirmation.
6. **Point-in-time:** all figures are 2026-06-13 snapshots; crypto moves fast.

---

## 6. What would change the verdict

**Upgrade to buy:** a public **fee/revenue** figure (DefiLlama Pro or Dune) showing usage
monetising; TVS trending up; Lasernet growth sustained (not a spike); discount to Pyth
narrowing on usage.
**Downgrade:** integrations stay "announced" with flat TVS/fees; Lasernet flat/falling;
Zest concentration unwinds; emissions dilute; competitors capture the RWA narrative.

---

## 7. Known data limitations

- **TVS is a single manual reading** ($148M) — the DefiLlama `/oracles` API is paywalled (Pro, $300/mo). No free TVS *history*, so TVS *growth* isn't yet tracked.
- **No fee/revenue data** — the decisive metric for the thesis is missing (paid: DefiLlama Pro / Dune / Token Terminal).
- **RWA count (20,000+) is DIA's own headline**, not independently verified; the free API only exposes a crypto-token floor.
- **Staking/grants are manual** — accurate as of the research date, not live.
- **Reach proxy remains in the tool** (now clearly labelled) because it shows *which* protocols touch DIA; it must not be read as secured value.

---

*Generated by the `dia-alpha-monitor` tool. Cross-check the live report (`python -m dia_alpha_monitor report`) and the linked sources before acting.*
