# Your Strategy: $50 → $100

These rules come from your answers. The code enforces them: `config.json` holds the numbers, `scanner/positions.py` gives HOLD/SELL calls.

## Budget
| Rule | Value | Why |
|---|---|---|
| Starting account | **$50** | |
| Goal | **$100** (2x) | |
| Most you're willing to lose | **$30** | Stop trading and review if the account drops to **$20** |
| Size per trade | **$20** | A 25% stop on $20 loses **$5** (10% of the account) |
| Coins held at once | **2 max** | $40 in play, $10 cash buffer for fees and slippage |
| Daily loss limit | **$10** | Two stopped-out trades = done for the day |

At $5 per losing trade, you can take about 6 straight losses before hitting the $30 limit. That buffer matters: most new traders' early trades lose while they learn.

## Exit rule (what you asked for)
1. **Before 2x:** sell if it falls **25%** below your buy price.
2. **Once it hits 2x:** the stop jumps up to **+30% gain** and never goes lower.
3. **As it keeps running:** the stop trails **35% below the highest price**, so at 5x the stop is 3.25x. You stay in while growth continues and still keep most of a big run.
4. **Early-exit warnings** (your call, not automatic): chart turns DOWNTREND, sellers outnumber buyers, holders falling, market cap or liquidity shrinking.

Suggestion, not required: at 2x, consider selling half. That takes your original $20 out, so the rest is free money and one trade can't turn a win into a loss.

## Buy low, sell high: how the chart check works
(You wrote "buy high, sell low". I'm assuming you meant the opposite. 🙂)
- **PULLBACK** = dip inside an uptrend (higher lows, down less than 30% from the high). Best entry.
- **UPTREND** = higher lows, price above its 20-hour average. OK entry.
- **EXTENDED** = price 50%+ above its average, a vertical pump. **Don't buy**: this is where late buyers become exit liquidity.
- **DOWNTREND** = lower lows, below average. Don't buy; if you hold it, consider exiting.
- "Always bounces back": the chart check reports `recovered_from_dip_pct`, meaning how much of its biggest drop the coin has regained. A coin that repeatedly recovers its dips scores better than one that doesn't.

## Trump, Elon and top traders: what's realistic
- **Trump:** the official $TRUMP coin launched in January 2025 at huge hype, then lost most of its value within months. $MELANIA did worse. So hype at launch did **not** mean steady growth. These coins can make money on a well-timed entry and exit, but they are not "always up".
- **Elon Musk** has never launched a meme coin. Every "Elon" coin is unofficial. His posts can briefly pump coins like DOGE or ones named after something he mentioned, and those pumps often reverse within hours.
- **Scam risk:** fake "official" Trump and Elon tokens appear constantly. **Only buy a contract address posted by the verified account itself**, never one from a reply, DM, or Telegram.
- The scanner searches and flags tokens with Trump/Elon keywords (`hype_keywords` in `config.json`) so you see them first. They still have to pass the same safety filters and chart check.
- **Top Fomo traders:** I can't see Fomo's leaderboard. Send me the wallet address of a trader you want to follow, and I can add a tracker for what that wallet buys and sells. Copying blindly is risky: by the time you see a big trader's buy, the price has often already moved.

## Honest odds
Nobody, me included, can reliably predict which meme coin will 2x. Turning $50 into $100 is possible with one or two good trades. It's also common to lose the $30. The journal (`python3 scanner/stats.py`) will show you, with real numbers, whether this approach is working for you. Give it about 20–30 trades before judging.
