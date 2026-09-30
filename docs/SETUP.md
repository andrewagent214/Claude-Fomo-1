# Setup Guide (about 15 minutes)

Do this once on the computer that will stay on. You don't need any coding experience: just copy and paste the commands.

## 1. Install Python
- **Windows:** download Python 3 from https://www.python.org/downloads/ and run the installer. **Tick "Add python.exe to PATH"** on the first screen.
- **Mac:** download it from the same page and run the installer.

In the commands below, Windows users type `py` where it says `python3`.

## 2. Download this project
1. Open https://github.com/andrewagent214/Claude-Fomo-1/archive/refs/heads/claude/serene-mayer-jcrdmd.zip. The ZIP downloads.
2. Unzip it into your Documents folder and rename the folder to `Claude-Fomo-1`. (If the link says 404, log in to GitHub first: the repo is yours and may be private.)

## 3. Open a terminal in that folder
- **Windows:** open the `Claude-Fomo-1` folder in File Explorer, click the address bar, type `cmd`, and press Enter.
- **Mac:** open Terminal and type `cd ~/Documents/Claude-Fomo-1`, then Enter.

Check that everything works:
```
python3 -m unittest discover -s tests
```
You should see `OK` at the end.

## 4. Phone alerts
1. Install the free **ntfy** app on your phone (App Store or Google Play).
2. In the terminal: `python3 scanner/watch.py --test`
3. It prints a topic name like `fomo-3f9a1c...`. In the ntfy app, tap **+**, type that exact name, and subscribe.
4. Run the test command again. Your phone should buzz with "Fomo alerts working ✅".

## 5. Start watch duty
```
python3 scanner/watch.py
```
Leave that window open. It checks your coins every 5 minutes and scans for new ones every 30.
- **Keep the computer awake.** Windows: Settings → System → Power → Sleep = **Never** (while plugged in). Mac: start it as `caffeinate -i python3 scanner/watch.py` instead.
- If the computer restarts, open the terminal and run the command again.

## 6. Every evening (9pm)
Open a second terminal window in the folder:
```
python3 scanner/evening.py
```
Open the newest file in `output/reports/` (it's named `evening_<date>.md`), or paste its contents to Claude.

## 7. When you buy a coin
Open `journal/positions.csv` in Notepad (Windows) or TextEdit (Mac) and add a line:
```
2026-10-01T21:15-07:00,TRUMPCAT,solana,PASTE_PAIR_ADDRESS_HERE,0.00123,20,0.00123,,first trade
```
| Field | What to put |
|---|---|
| date_opened | When you bought (`-07:00` = Pacific daylight time, `-08:00` in winter) |
| token | The coin's ticker |
| chain | `solana`, `base`, `bsc`, `ethereum` or `monad` |
| pair_address | The last part of the coin's DexScreener link: `dexscreener.com/solana/`**`this part`**. The scan report and buy alerts link to it. |
| entry_price | The price you paid per coin (USD) |
| size_usd | How much you spent (20) |
| peak_price | Same as entry_price. The watcher updates it. |
| holders | Optional: the holder count from the app. Add more later like `1200/1350`. |
| notes | Anything |

Save the file. The watcher picks it up on its next check.

## 8. When you sell
1. Delete the coin's line from `journal/positions.csv`.
2. Add a line to `journal/trades.csv`:
```
2026-10-02,TRUMPCAT,solana,<token address>,pullback,0.00123,0.00250,20,0.40,chart pullback + hype,2x floor hit,yes,
```
   The columns are: date, token, chain, token_address, setup, entry_price, exit_price, size_usd, fees_usd, entry_reason, exit_reason, rule_followed (yes/no), notes.
3. Run `python3 scanner/stats.py` to update your real performance numbers.
