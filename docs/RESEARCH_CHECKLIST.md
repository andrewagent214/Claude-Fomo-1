# Pre-Trade Research Checklist

Do this for every WATCH token before buying. **Any red flag = skip.** Record the result in the journal `notes` column.

## 1. Contract safety (red flags are instant skips)
The scan's **Safety** column runs RugCheck (Solana) and honeypot.is (Base, BNB, Ethereum) for you. FAIL tokens are already dropped. If it says **unchecked** (Monad, or the API was down), do this section by hand. OK only means no *known* trap was found, so still skim the items below.

- [ ] **Mint authority revoked.** On Solana, check with RugCheck, Solscan, or Birdeye. If it isn't revoked, the dev can print more tokens.
- [ ] **Freeze authority revoked.** If it isn't, the dev can freeze your tokens so you can't sell.
- [ ] **Liquidity locked or burned.** An unlocked LP can be pulled, which is a rug.
- [ ] **No honeypot or sell tax.** On EVM chains like Base, run a honeypot or tax checker.
- [ ] Pump.fun tokens: did it graduate to Raydium or PumpSwap? Know which pool you're trading.

## 2. Holder distribution
- [ ] Top 10 holders (excluding the LP and burn addresses) hold **< 30%**.
- [ ] Dev wallet holds **< 5%**, and it hasn't been selling.
- [ ] No cluster of wallets funded from one source (bundled or sniped launch). Bubblemaps shows these clusters.

## 3. Market structure (from the scan report)
- [ ] Liquidity ≥ the config minimum, and your position is **< 2% of pool liquidity** so you can get out.
- [ ] 1h buys ≥ sells, and volume isn't just a few wallets wash-trading.
- [ ] Chart check is PULLBACK or UPTREND, not EXTENDED. Late entries into vertical pumps are how buyers become exit liquidity.
- [ ] Chart: entering on a pullback or consolidation, not a vertical green candle.

## 4. Narrative & socials
- [ ] Real X or Telegram activity, not just bots. Account age and follower quality look organic.
- [ ] A clear narrative or meta: why would people keep buying this *this week*?
- [ ] Dev or team history: past launches that rugged?

## 5. The plan (write it down before you click buy)
- [ ] Position size from the scan report ($20 with the current config)
- [ ] Stop price
- [ ] 2x lock-in price and the +30% floor price (from the scan report)
- [ ] You're under the max open positions and haven't hit today's loss limit

## 6. Trump / Elon / celebrity coins (extra checks)
- [ ] The contract address came from the person's **verified** account or official site, not a reply, DM, or group chat.
- [ ] It's the same contract address the Fomo app shows. Copycats use the same name and ticker.
- [ ] You aren't buying in the first minutes after a post, when bots have already front-run the pump.
