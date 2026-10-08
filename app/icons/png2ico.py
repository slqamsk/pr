import sys
import os
from PIL import Image

INSTRUCTION = """
================================================================
  png2ico — конвертер PNG в ICO
================================================================

  Что делает:
    Берёт PNG-файл и создаёт рядом файл с тем же именем,
    но с расширением .ico, содержащий стандартный набор
    размеров: 16, 24, 32, 48, 64, 128, 256 пикселей.

  Использование:
    python png2ico.py <файл.png>

  Примеры:
    python png2ico.py icon_work.png
    python png2ico.py icon_idle.png
    python png2ico.py "C:\\path\\to\\icon.png"

  Требования к PNG:
    - квадратный (ширина = высота),
    - желательно 256x256 или больше,
    - с прозрачным фоном (альфа-канал),
      иначе иконка будет в белом квадрате.

  Если Pillow не установлен:
    python -m pip install pillow

  Если имя файла содержит пробелы — заключите его в кавычки:
    python png2ico.py "my icon.png"

================================================================
"""


def fail(msg: str = None):
    if msg:
        print(f"\nОшибка: {msg}")
    print(INSTRUCTION)
    sys.exit(1)


def main():
    if len(sys.argv) < 2:
        fail("не указан файл PNG")

    if len(sys.argv) > 2:
        fail("слишком много аргументов (обрабатывается только один файл)")

    png_path = sys.argv[1]

    if not os.path.isfile(png_path):
        fail(f"файл не найден: {png_path}")

    if not png_path.lower().endswith(".png"):
        fail(f"ожидается файл с расширением .png, получено: {png_path}")

    ico_path = os.path.splitext(png_path)[0] + ".ico"

    try:
        img = Image.open(png_path).convert("RGBA")
        img.save(ico_path, format="ICO",
                 sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                        (64, 64), (128, 128), (256, 256)])
    except Exception as e:
        fail(f"не удалось сконвертировать: {e}")

    print(f"Готово: {ico_path}")


if __name__ == "__main__":
    main()