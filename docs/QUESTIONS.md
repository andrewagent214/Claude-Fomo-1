# Setup Questions: your answers (Sept 2026)

| Question | Your answer | Set in |
|---|---|---|
| Capital | $50 to start, more later | `risk.account_size_usd` |
| Max loss | $30 total | `risk.total_loss_limit_usd` |
| Goal | $100 | `risk.goal_usd` |
| Hold time | As long as growth + hype continue | trailing stop, `risk.trail_from_peak_pct` |
| New launches? | Yes, if big hype/upside; also older coins with steady growth | `filters.min_age_minutes` = 15, `max_age_days` = 365 |
| After 2x | Stay in, never drop below +30% | `risk.lock_in_*` |
| Follow | Trump, Elon, top Fomo trader | `hype_keywords`; trader tracker waiting on a wallet address |
| Past trades | None yet | journal starts empty |
| When you're on | ~9–10pm Pacific, longer if something's moving | `scanner/evening.py` |

## Still open
1. Which chains does your Fomo account trade: Solana only, or Base too?
2. Wallet address(es) of the top Fomo trader(s) you want to follow.
3. Does the Fomo app let you set limit or stop-loss sell orders? This decides how safe it is to hold overnight.
