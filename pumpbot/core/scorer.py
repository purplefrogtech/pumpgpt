import numpy as np

def score_signal(rsi_last: float,
                 macd_last: float,
                 macd_sig_last: float,
                 volume_spike: float,
                 price_change_pct_5: float) -> int:
    """
    Basit bir puanlama:
    - RSI>60: +20, RSI>70: +35
    - MACD>Signal: +20
    - Hacim spike (x kat): +10...(min 0, max 30)
    - 5 barlık fiyat değişimi %: +0..30
    Max 100
    """
    score = 0
    if rsi_last > 70:
        score += 35
    elif rsi_last > 60:
        score += 20

    if macd_last > macd_sig_last:
        score += 20

    score += int(np.clip((volume_spike - 1.0) * 10.0, 0, 30))
    score += int(np.clip(price_change_pct_5 * 2.0, 0, 30))

    return int(np.clip(score, 0, 100))
