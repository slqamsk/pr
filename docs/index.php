<?php
// docs/index.php - Страница логина (только форма)
session_start();

// Если уже залогинен — сразу в профиль
if (isset($_SESSION['token'])) {
    header('Location: pages/profile.php');
    exit;
}

// Проверяем, есть ли ошибка из сессии (переданная из profile.php)
$loginError = $_SESSION['login_error'] ?? '';
unset($_SESSION['login_error']); // удаляем после чтения
?>
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Вход</title>
    <link rel="stylesheet" href="/pr/assets/css/style.css">
</head>
<body>
    <div class="container">
        <div class="box">
            <h1>🔐 Вход</h1>
            <form method="POST" action="pages/profile.php">
                <label for="username">Логин:</label>
                <input type="text" id="username" name="username" autocomplete="username" required>
                
                <label for="password">Пароль:</label>
                <input type="password" id="password" name="password" autocomplete="current-password" required>
                
                <button type="submit">Войти</button>
            </form>
            <?php if ($loginError): ?>
                <div class="error"><?= htmlspecialchars($loginError) ?></div>
            <?php endif; ?>
        </div>
    </div>
</body>
</html>