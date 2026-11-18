"""Звук ролика для Instagram: проверка и исправление. Обязателен перед публикацией любого видео
(ig_publish.py вызывает proverka сам и не публикует ролик с плохим звуком).

    python3 tools/zvuk.py proverka <видео>            → таблица и вердикт; код выхода 1, если звук не годится
    python3 tools/zvuk.py master <видео> [<выход>] [--zvonko]  → исправленный звук (видео не пережимается), потом повторная проверка;
                                                    --zvonko — максимально звонко и плотно (разборчивость −8,5, сильное сжатие)

Почему так (2026-11-06, ролик «Толпа умнее эксперта»): по громкости ролик был в норме (−14,2 LUFS), но на телефоне
звучал тише соседних рилсов. Instagram сам приводит все ролики к −14 LUFS (46 скачанных роликов блогеров — ровно
−14,1), поэтому слышимую разницу даёт не громкость, а РАЗБОРЧИВОСТЬ голоса: доля частот 2–5 кГц, которые играет
динамик телефона. У блогеров она −10…−12 дБ (к 100–500 Гц), у нас было −19 дБ: шумодав afftdn на тихой записи
срезал верх голоса (запись −12,6 → после шумодава −20,2). Нормы ниже взяты по роликам из Блогеры/.
"""
import json, re, subprocess, sys
from pathlib import Path
import numpy as np

# нормы (по 46 роликам блогеров: Хормози, Мартелл, Санчес, Хиггинс, Jessi Jean, …)
LUFS_MIN, LUFS_MAX = -15.0, -13.0      # общая громкость; Instagram всё равно приводит к −14
TP_MAX = -1.0                          # пики, dBTP (AAC при перекодировке добавляет 0,2–0,5 дБ)
PRES_MIN = -13.5                       # разборчивость: 2–5 кГц к 100–500 Гц, дБ (блогеры −10…−12,4)
PRES_TARGET = -11.0                    # куда поднимает master
SPEECH_MIN = -18.5                     # громкость окон с речью, дБ (блогеры −16…−17,4)


def pcm(path, af=None, sr=16000):
    cmd = ["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(sr)]
    if af:
        cmd += ["-af", af]
    out = subprocess.run(cmd + ["-f", "s16le", "-"], capture_output=True).stdout
    return np.frombuffer(out, np.int16).astype(float) / 32768


def rms_db(a):
    return 20 * np.log10(np.sqrt(np.mean(a ** 2)) + 1e-12)


def measure(path):
    err = subprocess.run(["ffmpeg", "-nostats", "-i", str(path), "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    tail = err[err.rfind("Summary:"):]
    lufs = float(re.search(r"I:\s+(-?[\d.]+) LUFS", tail).group(1))
    tp = float(re.search(r"Peak:\s+(-?[\d.inf]+) dBFS", tail).group(1))
    pres = rms_db(pcm(path, "highpass=f=2000,lowpass=f=5000")) - rms_db(pcm(path, "highpass=f=100,lowpass=f=500"))
    a = pcm(path); w = 6400
    win = np.array([rms_db(a[i:i + w]) for i in range(0, len(a) - w, w)])
    speech = float(np.median(win[win > np.percentile(win, 40)])) if len(win) else -99
    return {"lufs": lufs, "tp": tp, "pres": round(float(pres), 1), "speech": round(speech, 1)}


def verdict(m):
    bad = []
    if not LUFS_MIN <= m["lufs"] <= LUFS_MAX:
        bad.append(f"громкость {m['lufs']:.1f} LUFS (нужно {LUFS_MIN:g}…{LUFS_MAX:g})")
    if m["tp"] > TP_MAX:
        bad.append(f"пики {m['tp']:.1f} dBTP (нужно ≤ {TP_MAX:g})")
    if m["pres"] < PRES_MIN:
        bad.append(f"голос глухой: разборчивость {m['pres']:.1f} дБ (нужно ≥ {PRES_MIN:g}, у блогеров −10…−12) — на телефоне будет тише соседних рилсов")
    if m["speech"] < SPEECH_MIN:
        bad.append(f"речь тихая относительно музыки: {m['speech']:.1f} дБ (нужно ≥ {SPEECH_MIN:g})")
    return bad


def proverka(path, quiet=False):
    m = measure(path)
    bad = verdict(m)
    if not quiet:
        print(f"{Path(path).name}: громкость {m['lufs']:.1f} LUFS · пики {m['tp']:.1f} dBTP · "
              f"речь {m['speech']:.1f} дБ · разборчивость {m['pres']:.1f} дБ")
        print("  ✅ звук годится для Instagram" if not bad else "  ❌ " + "\n  ❌ ".join(bad))
    return m, bad


def master(src, dst=None, zvonko=False):
    """Разборчивость — подъём полосы 2–5 кГц до PRES_TARGET; лёгкое уплотнение; громкость −14 LUFS, пики ≤ −1,5.
    zvonko (Арон, 2026-11-11: «чтобы очень звонко звучал, насколько это возможно»): разборчивость до −8,5,
    плотное сжатие (тихие слова подтянуты к громким), деэссер — громче на слух при тех же −14 LUFS,
    до которых Instagram всё равно приводит ролик."""
    src = Path(src); dst = Path(dst) if dst else src.with_name(src.stem + "_звук" + src.suffix)
    m = measure(src)
    boost = float(np.clip((-8.5 if zvonko else PRES_TARGET) - m["pres"], 0, 10))
    eq = (f"equalizer=f=3200:t=q:w=0.9:g={boost:.1f},equalizer=f=6500:t=q:w=1:g={boost * 0.4:.1f}," if boost > 0.3 else "")
    pre = (f"highpass=f=70,{eq}"
           "acompressor=threshold=-22dB:ratio=2.5:attack=8:release=120:makeup=2:knee=4")
    if zvonko:
        pre = (f"highpass=f=80,{eq}deesser=i=0.35:m=0.5:f=0.5,"
               "acompressor=threshold=-28dB:ratio=4:attack=5:release=90:makeup=4:knee=6,"
               "acompressor=threshold=-14dB:ratio=3:attack=2:release=50:knee=3")
    j = subprocess.run(["ffmpeg", "-nostats", "-i", str(src), "-vn", "-af", pre + ",loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json",
                        "-f", "null", "-"], capture_output=True, text=True).stderr
    L = json.loads(j[j.rfind("{"):j.rfind("}") + 1])
    af = (pre + f",loudnorm=I=-14:TP=-1.5:LRA=11:linear=true:measured_I={L['input_i']}:measured_TP={L['input_tp']}:"
          f"measured_LRA={L['input_lra']}:measured_thresh={L['input_thresh']}:offset={L['target_offset']},aresample=48000")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-c:v", "copy", "-af", af, "-c:a", "aac", "-b:a", "256k",
                    "-movflags", "+faststart", str(dst)], check=True)
    print(f"было: разборчивость {m['pres']:.1f} дБ, громкость {m['lufs']:.1f} LUFS → подъём 2–5 кГц {boost:+.1f} дБ")
    m2, bad = proverka(dst)
    if bad and any("громкость" in b for b in bad):   # linear-режим упёрся в пики — добить ограничителем
        tmp = dst.with_name(dst.stem + "_tmp" + dst.suffix)
        gain = -14 - m2["lufs"]
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(dst), "-c:v", "copy", "-af",
                        f"aresample=192000,volume={gain:.2f}dB,alimiter=limit=0.82:attack=1:release=60:level=false:latency=1,aresample=48000",
                        "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", str(tmp)], check=True)
        tmp.replace(dst); proverka(dst)
    return dst


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in ("proverka", "master"):
        sys.exit(__doc__)
    if sys.argv[1] == "proverka":
        sys.exit(1 if proverka(sys.argv[2])[1] else 0)
    a = [x for x in sys.argv[2:] if x != "--zvonko"]
    master(a[0], a[1] if len(a) > 1 else None, zvonko="--zvonko" in sys.argv)
