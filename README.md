# gta6-twitch-ccu-forecaster-2

[![make.fun · gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/urelkdubdqwr/gta6-twitch-ccu-forecaster-2/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/urelkdubdqwr/gta6-twitch-ccu-forecaster-2/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)

Forecasts Grand Theft Auto VI's launch-day Twitch concurrent viewers for hours 2-24 of 2026-11-19 (UTC) as five quantiles per hour: a conditional linear shape on log hour-1 viewers over the launch comparables, corrected by the target's own pre-launch category diurnal rhythm relative to the comparables' own pre-launch rhythms, and a size-window empirical spread blended with a normal. Deterministic per case. Python 3.13, standard library only, offline.

## Run it

```sh
MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

---

<sub>Entered on [make.fun](https://make.fun/bounty/gta6-twitch-ccu-forecast-01) for the Forecast GTA VI's launch-day Twitch viewers hour by hour bounty.</sub>
