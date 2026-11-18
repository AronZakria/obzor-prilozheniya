#!/bin/bash
# Установка всего, что нужно для монтажа, без пароля от компьютера: всё ставится в домашнюю папку.
# Запуск (Codex делает это сам, в фоне):  nohup bash ustanovka.sh > ustanovka.log 2>&1 &
# Повторный запуск безопасен: что уже стоит, пропускается. Последняя строка лога — «ГОТОВО» или «НЕ ХВАТАЕТ: …».
# Потом перед командами монтажа:  source env.sh   (добавляет ~/.local/bin и окружение .venv в PATH)

set -u
N="$(cd "$(dirname "$0")" && pwd)"
L="$HOME/.local"
mkdir -p "$L/bin"
export PATH="$L/bin:$L/node/bin:$PATH"
ARCH="$(uname -m)"          # arm64 — Apple Silicon, x86_64 — Intel
OS="$(uname -s)"            # Darwin — macOS
NET="${TMPDIR:-/tmp}/ustanovka.$$"
mkdir -p "$NET"
MISSING=()

shag() { echo; echo "== $*"; }
est()  { command -v "$1" >/dev/null 2>&1; }

shag "Система: $OS $ARCH"
[ "$OS" = "Darwin" ] || echo "Это не macOS: скрипт рассчитан на Mac. На Windows ставь Python, ffmpeg (winget) и faster-whisper по montazh.md."

# 1. Инструменты разработчика (swift, git). Ставит macOS по окну «Установить» — пароль не нужен.
shag "Инструменты разработчика (Xcode Command Line Tools)"
if xcode-select -p >/dev/null 2>&1; then
  echo "есть"
else
  xcode-select --install >/dev/null 2>&1
  echo "НУЖНО ОТ ЧЕЛОВЕКА: в окне macOS нажать «Установить» (10–15 минут). Потом запустить ustanovka.sh ещё раз."
  MISSING+=("инструменты разработчика")
fi

# 2. uv — ставит Python и библиотеки в домашнюю папку
shag "uv (Python без пароля)"
if est uv; then echo "есть: $(uv --version)"; else
  curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="$L/bin" INSTALLER_NO_MODIFY_PATH=1 sh && echo "поставлен" || MISSING+=("uv")
fi

# 3. Окружение .venv с расшифровкой речи
shag "Python 3.12 и библиотеки в $N/.venv"
if [ ! -x "$N/.venv/bin/python" ]; then uv venv --python 3.12 "$N/.venv" || MISSING+=("python"); fi
REQ="$N/requirements.txt"
if [ "$ARCH" != "arm64" ] || [ "$OS" != "Darwin" ]; then
  sed 's/^mlx-whisper$/faster-whisper/' "$N/requirements.txt" > "$NET/req.txt"; REQ="$NET/req.txt"
  echo "не Apple Silicon: вместо mlx-whisper ставлю faster-whisper (расшифровку в montazh.py нужно переключить на него)"
fi
uv pip install --python "$N/.venv/bin/python" -r "$REQ" -q && echo "библиотеки на месте" || MISSING+=("библиотеки python")

# 4. ffmpeg и ffprobe
shag "ffmpeg и ffprobe"
if est ffmpeg && est ffprobe; then echo "есть: $(ffmpeg -version | head -1)"
elif est brew; then brew install ffmpeg && echo "поставлен через Homebrew" || MISSING+=("ffmpeg")
else
  # conda-forge собирает ffmpeg под Apple Silicon и Intel, с libx264; micromamba — один файл, без пароля
  PLAT="osx-arm64"; [ "$ARCH" = "x86_64" ] && PLAT="osx-64"
  curl -Ls "https://micro.mamba.pm/api/micromamba/$PLAT/latest" | tar -xj -C "$NET" bin/micromamba
  for i in 1 2 3; do   # сеть бывает нестабильной: до трёх попыток
    "$NET/bin/micromamba" create -y -q -r "$L/mamba" -p "$L/ffmpeg" -c conda-forge ffmpeg >/dev/null 2>&1 && [ -x "$L/ffmpeg/bin/ffprobe" ] && break
    echo "попытка $i не удалась, повторяю"; rm -rf "$L/ffmpeg"
  done
  if [ -x "$L/ffmpeg/bin/ffprobe" ]; then
    ln -sf "$L/ffmpeg/bin/ffmpeg" "$L/bin/ffmpeg" && ln -sf "$L/ffmpeg/bin/ffprobe" "$L/bin/ffprobe"
    echo "поставлен из conda-forge: $(ffmpeg -version | head -1)"
  else MISSING+=("ffmpeg"); fi
fi

# 5. Node.js 22+
shag "Node.js 22+"
NODE_OK=0
if est node && [ "$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)" -ge 22 ]; then NODE_OK=1; echo "есть: $(node -v)"; fi
if [ $NODE_OK = 0 ]; then
  NA="arm64"; [ "$ARCH" = "x86_64" ] && NA="x64"
  F="$(curl -s https://nodejs.org/dist/latest-v22.x/SHASUMS256.txt | awk '{print $2}' | grep "darwin-$NA.tar.gz$" | head -1)"
  if [ -n "$F" ] && curl -Ls "https://nodejs.org/dist/latest-v22.x/$F" | tar -xz -C "$NET"; then
    rm -rf "$L/node" && mv "$NET/${F%.tar.gz}" "$L/node" && echo "поставлен: $(node -v)"
  else MISSING+=("node"); fi
fi

# 6. Запись экрана сайта (Playwright + Chromium) — в папке набора
shag "Playwright и Chromium"
if est npm; then
  (cd "$N" && { [ -d node_modules/playwright ] || npm i --no-audit --no-fund -s playwright@1; } && npx -y playwright install chromium >/dev/null && echo "готово") || MISSING+=("playwright")
fi

# 7. HyperFrames (анимация из кода) — прогреть, чтобы первый запуск был быстрым
shag "HyperFrames"
if est npx; then npx -y hyperframes@latest --version 2>/dev/null && echo "готово" || echo "не прогрелся — не страшно, скачается при первом использовании"; fi

# 8. Слежение за глазами и размытие (macOS Vision) — нужны инструменты разработчика
shag "Программы на Swift (tools/build.sh)"
if est swiftc && [ "$OS" = "Darwin" ]; then sh "$N/tools/build.sh" >/dev/null 2>&1 && echo "собраны" || MISSING+=("swift-инструменты")
else echo "пропущено: нет swiftc (поставь инструменты разработчика и запусти скрипт ещё раз)"; fi

# 9. Шрифты для титров
shag "Шрифты"
if [ "$OS" = "Darwin" ]; then mkdir -p "$HOME/Library/Fonts" && cp -n "$N"/tools/fonts/*.ttf "$HOME/Library/Fonts/" 2>/dev/null; echo "Prata и Montserrat в ~/Library/Fonts"; fi

# 10. Модель расшифровки (около 1,6 ГБ) — скачать заранее
shag "Модель whisper-large-v3-turbo"
if [ "$ARCH" = "arm64" ] && [ "$OS" = "Darwin" ]; then
  "$N/.venv/bin/python" -c "from huggingface_hub import snapshot_download as s; s('mlx-community/whisper-large-v3-turbo')" >/dev/null 2>&1 \
    && echo "скачана" || MISSING+=("модель whisper")
fi

# Окружение для команд монтажа
cat > "$N/env.sh" <<EOF
export PATH="$L/bin:$L/node/bin:$N/.venv/bin:\$PATH"
EOF

rm -rf "$NET"
echo
if [ ${#MISSING[@]} -eq 0 ]; then echo "ГОТОВО"; else echo "НЕ ХВАТАЕТ: ${MISSING[*]}"; fi
