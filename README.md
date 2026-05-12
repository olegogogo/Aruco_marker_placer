# Aruco Marker Placer

Приложение для размещения ArUco-маркеров на чертеже/изображении и экспорта проекта.

## Что умеет
- Загрузка фонового изображения.
- Выбор словаря ArUco, `id`, размера на фоне (`px`), реального размера (`mm`) и поворота (`yaw`).
- Размещение маркеров кликом по картинке.
- Импорт схемы из `json` формата как в `scheme(5).json`.
- Сохранение проекта в папку:
  - `scheme.json` в формате:
    - `sizeX`, `sizeY`, `pixelCountPerMeter`, `colorInverted`, `markers[]`
  - `layout.preview.png` (превью раскладки на фоне)
  - отдельные изображения маркеров: `id<id>_<size_mm>mm.png` и `id<id>_<size_mm>mm.svg`

## Координаты
- В `json` координаты маркера (`x`, `y`) сохраняются в метрах.
- Нулевая точка: центр фонового изображения.
- `x`: вправо положительное.
- `y`: вверх положительное.
- Пересчет делает `pixelCountPerMeter`.

## Установка
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Запуск
```bash
python3 app.py
```

## Пример JSON
```json
{
  "sizeX": 0.9,
  "sizeY": 0.9,
  "pixelCountPerMeter": 2500,
  "colorInverted": true,
  "markers": [
    {
      "id": 9,
      "type": "Aruco_4x4_50",
      "x": 0.33,
      "y": -0.33,
      "size": 0.22,
      "yaw": 0.0
    }
  ]
}
```
