<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>✅ Деплой работает</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; background: #f0f8ff; }
        .box { background: white; padding: 30px; border-radius: 10px; box-shadow: 0 0 20px rgba(0,0,0,0.1); }
        .ok { color: #2e7d32; font-weight: bold; }
        .info { background: #e3f2fd; padding: 15px; border-radius: 5px; margin: 10px 0; }
        hr { border: 1px solid #ddd; }
    </style>
</head>
<body>
    <div class="box">
        <h1>✅ Деплой работает!</h1>
        <div class="info">
            <p><strong>Сервер:</strong> <?= $_SERVER['SERVER_SOFTWARE'] ?></p>
            <p><strong>Время:</strong> <?= date('d.m.Y H:i:s') ?></p>
            <p><strong>PHP:</strong> <?= phpversion() ?></p>
        </div>
        <hr>
        <p class="ok">✔ Автоматический деплой из GitHub Actions настроен успешно!</p>
        <p>Файлов в папке: <?= count(scandir(__DIR__)) - 2 ?></p>
        <p><small>Последнее обновление: <?= date('d.m.Y H:i:s') ?></small></p>
    </div>
</body>
</html>