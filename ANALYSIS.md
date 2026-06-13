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
| **Official DIA oracle TVS** | **$112.48M** (mcap/TVS **0.13×**) | **DefiLlama Pro `/api/oracles` (live)** | High — live API, 1,833d history |
| TVS trend | **7d +2.4% · 30d −20.7% · 90d −10.4% · ~−26% YoY** | DefiLlama Pro (live) | High |
| DIA share of all-oracle TVS | **0.228%** of $49.4B (≈flat YoY) | DefiLlama Pro (live) | High |
| TVS concentration | **Zest V2 ~63% (Stacks), Hydration ~25% (Polkadot); top-2 ≈ 88%** | DefiLlama Pro (live) | High |
| Lasernet throughput (daily tx) | 313,152 · **+53% 7d / +45% 30d** | explorer.diadata.org (Blockscout) | High — on-chain, 31d history |
| DIA feed coverage | 5,859 crypto feeds, 102 chains, 83 active scrapers | DIA API | High |
| DIA RWA assets (reported) | 20,000+ | diadata.org (manual) | Low — DIA's own headline, not independently counted |
| Staking | 4.4M DIA, 11 feeders, 12.56% APY (→5-6% Jul 1) | DIA blog (manual, 2026-06-05) | Med |
| Mainnet grants/integrations | 8 (100% to-mainnet), 1 new in 30d | manual, DIA-sourced | Med |
| Price momentum | 1d -1.6%, 7d -4.0%, **30d -38.5%** | CoinGecko | High |
| Alpha score (tool) | 54.8 / 100 | computed | — |

**Competitor market caps:** Chainlink $5.73B · Pyth $294.73M · RedStone $39.52M · API3 $36.35M · Chronicle (no liquid token).
**DIA vs peers by MARKET CAP:** 0.26% of Chainlink · ~5.0% of Pyth · ~37% of RedStone · ~40% of API3.
**DIA vs peers by TVS** (same DefiLlama Pro dataset — secured value, a different and more sobering picture): Chainlink $29.4B · Chronicle $7.40B · RedStone $3.22B · Pyth $2.26B · Switchboard $493M · Supra $160M · Band $118M · **DIA $112.5M** · API3 $19.9M. So by **secured value** DIA is **0.38% of Chainlink · 3.5% of RedStone · 5.0% of Pyth**, but **5.6× API3**. Note RedStone secures ~29× DIA's value on a *smaller* token — TVS and token price are only loosely linked.

---

## 2. The single most important correction

The tool originally reported a **"DIA-linked TVL proxy" of $11.30B gross / $2.31B
confidence-weighted.** That is **NOT** what DIA secures. It is the *whole* TVL of
every protocol that uses DIA *somewhere* (e.g. Morpho's entire ~$10B), which is an
**upper bound on reach**, not secured value.

DefiLlama's official per-oracle TVS — which counts only the markets/pools DIA
actually secures — is **$112.48M** (live, 2026-06-13). So:

- The reach proxy ($11.30B gross) **overstates DIA's real secured value by ~100× (gross) / ~20× (weighted)**.
- The report has been **recalibrated** (§3) to lead with the live official TVS
  and label the proxy explicitly as reach, not secured value.

**Implication:** DIA's real on-chain footprint is **modest (~$112M secured)** — small
versus Chainlink ($29B) — and **not currently growing** (−21% over 30d, ≈flat YoY).
Any bull case must rest on *future* growth, not current scale or recent trend.

---

## 3. Is it a buy? (verdict: speculative accumulate)

The setup is **asymmetric but unproven**:

**For (constructive, evidence-backed):**
- **Cheap vs peers:** $14.62M mcap = 0.37–0.40× of API3/RedStone *by mcap* despite arguably broader product (RWA, Lasernet rollup, VRF, 20-chain grants).
- **Cheap vs its own secured value:** mcap/TVS = **0.13×**.
- **Usage is growing where it's most trustless:** Lasernet throughput **+45% in 30 days** — hard, on-chain evidence the oracle is being *called* more (note: this is NOT yet showing up in secured value — see Against).
- **Real adoption:** $112M TVS across real protocols; 8 mainnet integrations; active RWA shipping (hemiBTC, Hermetica, Parallel, River).
- **Token utility transitioning:** Lasernet gas + staking (4.4M staked, rising).
- **Confirmed real revenue (firmer floor):** DIA states most revenue is *bespoke NDA enterprise contracts* (undisclosed) — i.e. a real, paying-customer business, not a pure subsidy story. Lowers go-to-zero/abandonment risk and corroborates the institutional pivot, even though it doesn't accrue to the token yet (§7).

**Against (risks / unproven):**
- **Momentum is negative:** −38.5% over 30d (price) — catching a falling knife.
- **TVS is shrinking, not growing:** with live history now available, secured value is **−21% over 30d, −10% over 90d, ≈−26% YoY** — and DIA's **share of all-oracle TVS is flat at ~0.23%**. The Lasernet call-volume growth is **not** translating into more value secured. This is the single biggest update vs the prior (manual $148M) read.
- **Small absolute scale:** $112M TVS is tiny in oracle terms (0.38% of Chainlink).
- **Monetisation reaches the company, not (yet) the token:** DIA confirms it earns real revenue — *bespoke NDA enterprise contracts* — but it's undisclosed and **off-chain**, so it does not flow to $DIA via Lasernet gas/staking. Token value capture needs a **discretionary buyback/revenue-share**, which is not active on-chain (no burn/buyback evidenced). So usage→*token* value stays unproven even though the business earns. Bonus concern: undisclosed revenue is **unvaluable and opaque** — ironic for a "don't trust, verify" project (§7).
- **Severe concentration risk:** the live per-protocol breakdown is **worse than the old "~48% Zest" reading** — **Zest V2 alone is ~63% of TVS (on Stacks) and Hydration ~25% (on Polkadot); the top two are ~88%**. A single Zest unwind would roughly halve DIA's secured value, and ~89% sits on two non-EVM-mainstream chains.
- **The proxy lesson:** headline "adoption" numbers can be 20–100× too generous; treat all reach/announcement metrics with suspicion.

**Verdict:** at $0.12 the risk/reward is still **skewed for a small, thesis-driven
position** — a deep discount with real (if concentrated) usage and one genuine growth
signal (Lasernet) — but the live TVS data **weakens** the case vs the prior read: secured
value is falling, share is flat, and 88% rests on two protocols. It is **not** a
high-conviction buy. Best expressed as a **small, sized, averaged-in accumulate**, now
explicitly contingent on (a) the usage→fees link being proven AND (b) TVS stabilising/
re-growing and **diversifying beyond Zest**.

---

## 4. Fair value range (with the math, so it can be challenged)

Implied price = target market cap ÷ 119.68M circulating supply.

| Method | Anchor | Implied mcap | **Implied price** | vs $0.1223 | Notes |
|---|---|---|---|---|---|
| **Peer parity** (most defensible) | = API3/RedStone ($36–40M) | $36–40M | **$0.30–0.33** | 2.5–2.7× | DIA's nearest liquid peers; comparable/broader product |
| **TVS multiple** (cross-check) | 0.3–0.5× of $112.5M TVS | $34–56M | **$0.28–0.47** | 2.3–3.9× | Heuristic — TVS is not revenue; lower than before as TVS fell |
| **Pyth fraction** | 10% of Pyth | $29.5M | $0.25 | 2.0× | Modest |
| **Chainlink fraction** (bull) | 1–2.5% of Chainlink | $57–143M | **$0.48–1.20** | 3.9–9.8× | Requires real oracle-share capture |

**Fair-value range: ~$0.28–0.47 (base, ≈2.3–3.9×)**, anchored to peer-parity and a
conservative TVS multiple (the TVS-multiple row stepped down with the lower live $112.5M
TVS). **Bull extension to ~$1.20 (≈10×)** if DIA captures 1–2.5% of Chainlink-scale share
as the RWA/usage thesis pays off — but the flat oracle-share trend (0.23%) makes this
**less supported** by current data. **Downside floor ~$0.08–0.12** if the thesis stalls
(real assets/usage limit how far it falls, but a governance-only token with no fee capture
could stay here).

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

**Upgrade to buy:** a public **fee/revenue** figure (Dune / Token Terminal — *not*
DefiLlama, which doesn't cover oracle fees) showing usage monetising; **live TVS turning
up** (now directly trackable) and DIA's oracle-market share rising off 0.23%; Lasernet
growth sustained (not a spike); TVS diversifying beyond the Zest/Hydration pair.
**Downgrade:** integrations stay "announced" with flat/falling live TVS; Lasernet
flat/falling; the Zest ~63% position unwinds; emissions dilute; competitors capture the
RWA narrative.

---

## 8. What DefiLlama Pro adds to the case (and what it doesn't)

The Pro `/api/oracles` endpoint is now wired in (live). What it materially changes:

**It resolves the biggest prior data gap — TVS is no longer a single manual number.**
We now have a **1,833-day** TVS series, a **per-protocol/per-chain breakdown**, and DIA's
**share of the whole $49.4B oracle market**, all live. Three things it reveals:

1. **TVS is flat-to-falling, not growing** — −21% (30d), −10% (90d), ≈−26% YoY; share
   stuck at ~0.23%. This is the most important new fact: the Lasernet *call-volume* growth
   (+45%) is **not** translating into more *value secured*. It tempers the bull case.
2. **Concentration is worse than believed.** The breakdown shows **Zest V2 ≈ 63%** of TVS
   (Stacks) and **Hydration ≈ 25%** (Polkadot) — **top-2 ≈ 88%**, ~89% on two non-EVM
   chains. The earlier "~48% Zest" reading understated single-protocol risk.
3. **Apples-to-apples peer TVS.** Same dataset ranks every oracle by secured value:
   Chainlink $29.4B, Chronicle $7.4B, RedStone $3.2B, Pyth $2.3B … **DIA $112.5M**, API3
   $20M. DIA is bigger than API3 but a *fraction* of RedStone/Pyth by secured value — a
   sharper comparison than market cap alone.

**What Pro does NOT add:** the decisive metric — **oracle fee/revenue** — because
DefiLlama's fees dataset excludes oracles (`/api/summary/fees/dia` → 404). So Pro sharpens
the *adoption/scale* picture and finally lets us watch TVS over time, but the
**usage→monetisation link still has to come from elsewhere** (Dune / Token Terminal /
on-chain Lasernet accounting). Net effect: Pro makes the case **more honest and slightly
more cautious**, not more bullish.

---

## 7. Known data limitations

- ~~**TVS is a single manual reading** — no history.~~ **RESOLVED:** with the DefiLlama Pro key the tool now fetches the live per-oracle TVS series (1,833 days), so TVS *level, trend and oracle-market share* are all tracked. The live figure ($112.5M) is also **lower** than the earlier manual $148M reading.
- **No fee/revenue figure exists anywhere — and that's structural, not a sourcing gap.** Confirmed via DefiLlama (oracles aren't in the fees dataset; `/api/summary/fees/dia` → 404) *and* an independent 12-month sweep. The reason: during the grants phase DIA's oracles are **free** (up to 12 months across 20+ chains). Crucially, the value-capture mechanism **is designed but dormant** — DIA states *"network fees generated through increased oracle adoption are fed back into DIA Lasernet, incentivising stakers."* So the flywheel (oracle fees → Lasernet → stakers) is **built but switched off**. The re-rating trigger is therefore specific: **grants→paid conversion turning fee flow on**, with staking yield shifting from emission-funded to fee-funded. Nearest read: the **Jun–Jul 2026** window (first grant cohort matures + Jul 1 staking recalibration 30%→5–6%). **Triangulated five ways** (DefiLlama, Token Terminal, the Lasernet Blockscout explorer, direct RPC reads of the fee-hook contracts, and DIA's own docs/AMA): the only on-chain fee surface — Lasernet gas — is **~1.1 DIA/day (~$0.14/day, ~$50/yr)**, matching Token Terminal's *$2.80 of gas per 30 days*, and it's **internal network gas, not customer revenue**. **Confirmed nuance (DIA, direct, Jun 2026):** DIA states *"most of the revenue comes from customized deals and contracts under NDA; we do not disclose those revenue details."* So DIA-the-*company* **does** have real revenue (bespoke, enterprise, off-chain) — but it is (a) **unquantifiable** (NDA, no figure) and (b) **off-chain fiat/stablecoin that never touches Lasernet gas or reaches stakers**. The only path from it to the token is a **discretionary buyback / revenue-share**, which on-chain is **not active** (no burn; no evidenced buyback). So "Is DIA a real business?" → **yes (now confirmed)**; "does $DIA capture that?" → **not unless management chooses to route it via buybacks.** ⚠️ **Implication for the §6b tripwire:** it tracks the *on-chain* fee surface, so it will **not** see this off-chain NDA revenue — the truer token-value signal is a buyback/revenue-share announcement or treasury market-buys (treasury address undisclosed).
- **No public token-unlock schedule.** Supply is fixed (200M premined 2020, no minting). On-chain check (Ethereum, contract `0x84cA…c9419`): `totalSupply()` still reads the full **200M**, with **~31.27M parked at `0xdEaD`** (why CoinGecko shows ~168.8M "total") and **0 at `0x0`** — i.e. a one-time static removal, **no live burn mechanism**, so DIA is *not* deflationary and nothing offsets staking emissions. Circulating **119.68M**. The real near-term overhang is therefore **~49M locked (~$6M at $0.12)** — *not* the "200M − 120M = 80M" some sources cite (that double-counts burns). Modest in dollar terms, but **no granular vesting/cliff schedule is published on any tracker** (Tokenomist/DefiLlama-unlocks don't list DIA), so the overhang is **unmodellable** — a tail risk and a minor maturity/governance flag for a $15M-mcap token.
- **RWA count (20,000+) is DIA's own headline**, not independently verified; the free API only exposes a crypto-token floor.
- **Staking/grants are manual** — accurate as of the research date, not live.
- **Reach proxy remains in the tool** (now clearly labelled) because it shows *which* protocols touch DIA; it must not be read as secured value.

---

## 9. Community & external-sentiment scan (2026-06-13)

Cross-checked forums, Reddit, governance, exchange/listing history, incident
history and an independent 12-month news sweep. Findings:

- **Under-followed / low retail attention.** Repeated Reddit/forum searches found
  *no* meaningful community discussion despite a claimed "100,000+ followers."
  Double-edged: it's the asymmetry setup (no crowd → a catalyst could re-rate
  fast) **and** the reason momentum is weak and the discount persists (no retail bid).
- **Governance looks largely dormant.** No active/recent Snapshot proposals or
  live forum threads surfaced. A quiet DAO is *less* likely to pass the
  value-accrual proposal (fee switch / revenue share) the thesis needs.
- **Adoption breadth ≠ economic traction.** DIA markets **250+ "data/oracle
  users"** but DefiLlama attributes measurable TVS to only **~47 protocols**, two
  of which hold ~88%. The gap is the free-grants dynamic in numbers.
- **Clean record.** No hacks, exploits, delistings, lawsuits or team-dump
  controversies found; established team (building since 2018), open-source repo.
- **No *new* exchange catalyst.** On Coinbase/Binance/OKX since ~2022; the
  CF Benchmarks tie-up sometimes cited is from **Feb 2022**, not recent.
- **TVS figure discipline.** A third-party site claims "$400M TVS (7×)"; this is
  unreliable SEO — DefiLlama (authoritative) shows **$112.5M**, and DIA's own
  About page reports no TVS. Use $112.5M.
- **Independent confirmation of the core gap.** A comprehensive external 12-month
  roundup found **no fee/revenue/value-capture mechanism anywhere** — corroborating
  that the decisive metric is genuinely absent, not just missing from our sources.
- **Strongest "pivot is real" datapoint:** Particula's Digital Asset Risk Passport
  (Mar 2026) — DIA as oracle layer for institutional risk-rating + PoR of tokenised
  fixed-income/equity (Ethereum+Solana). Concrete institutional RWA infra, but
  still no disclosed AUM or fees.
- **Team & key-person read.** Strategy is coherent and well-articulated by senior
  leads (Hanson/BD, Marazas/Product) who speak fluent TradFi valuation (NAV,
  mark-to-model, reserve verification) — the right toolkit for the institutional
  pivot; clean two-product framing (Market = liquid, Value = illiquid/fundamental).
  **Soft flag:** CEO (Weber) and CTO (Brack) have low public visibility over the last
  12 months (comms delegated to core-team bylines), with co-founder Claudius the
  external face. No departures (Weber spoke at the Jun-2026 AI Infra Summit), so
  logged as a mild key-person/engagement risk, not a red flag. Notably, **no
  founder/senior-team communication in 12 months mentions token value-capture or
  fees** — confirming the monetization gap is strategic, not merely unannounced.

**Net:** the scan reinforces the existing verdict — a quiet, legitimate,
under-the-radar small-cap with a real (and increasingly institutional) product
and no crowd: a *catalyst-or-nothing* bet. Nothing here moves fair value; only
real fee/revenue data or a named AUM customer would.

---

*Generated by the `dia-alpha-monitor` tool. Cross-check the live report (`python -m dia_alpha_monitor report`) and the linked sources before acting.*
