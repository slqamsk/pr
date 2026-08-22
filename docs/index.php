<?php
// docs/index.php - Страница логина
session_start();

// Если пользователь уже авторизован, перенаправляем на профиль
if (isset($_SESSION['token'])) {
    header('Location: pages/profile.php');
    exit;
}

// Проверяем, пришёл ли запрос на логин
$loginError = '';
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['username']) && isset($_POST['password'])) {
    $username = $_POST['username'];
    $password = $_POST['password'];
    
    // Отправляем запрос к API
    $ch = curl_init('https://slqa.ru/pr/api/login/');
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_POST, true);
    curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode([
        'username' => $username,
        'password' => $password
    ]));
    curl_setopt($ch, CURLOPT_HTTPHEADER, [
        'Content-Type: application/json'
    ]);
    
    $response = curl_exec($ch);
    $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
    
    if ($httpCode === 200) {
        $data = json_decode($response, true);
        if (isset($data['token'])) {
            $_SESSION['token'] = $data['token'];
            header('Location: pages/profile.php');
            exit;
        }
    } else {
        $loginError = 'Неверный логин или пароль';
    }
}
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
            <form method="POST">
                <label for="username">Логин:</label>
                <input type="text" id="username" name="username" required>
                
                <label for="password">Пароль:</label>
                <input type="password" id="password" name="password" required>
                
                <button type="submit">Войти</button>
            </form>
            <?php if ($loginError): ?>
                <div class="error"><?= htmlspecialchars($loginError) ?></div>
            <?php endif; ?>
        </div>
    </div>
</body>
</html>