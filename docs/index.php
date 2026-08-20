<?php
require_once __DIR__ . '/config/database.php';
?>
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>✅ Сайт работает</title>
</head>
<body>
    <h1>✅ Деплой работает!</h1>
    <?php if ($dbConnected): ?>
        <p style="color: green;">✔ Подключение к БД успешно!</p>
        <p>Хост: <?= htmlspecialchars(getenv('DB_HOST')) ?></p>
        <p>База: <?= htmlspecialchars(getenv('DB_NAME')) ?></p>
    <?php else: ?>
        <p style="color: red;">✘ Ошибка БД: <?= htmlspecialchars($dbError) ?></p>
    <?php endif; ?>
</body>
</html>