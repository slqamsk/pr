<?php
// docs/pages/profile.php - Страница профиля + обработка логина
session_start();

// Если пришли POST-данные (логин), пытаемся авторизоваться
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['username'], $_POST['password'])) {
    $username = $_POST['username'];
    $password = $_POST['password'];
    
    $ch = curl_init('https://slqa.ru/pr/api/login/');
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_POST, true);
    curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode([
        'username' => $username,
        'password' => $password
    ]));
    curl_setopt($ch, CURLOPT_HTTPHEADER, ['Content-Type: application/json']);
    
    $response = curl_exec($ch);
    $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
    
    if ($httpCode === 200) {
        $data = json_decode($response, true);
        if (isset($data['token'])) {
            $_SESSION['token'] = $data['token'];
            header('Location: profile.php');
            exit;
        }
    }
    
    $_SESSION['login_error'] = 'Неверный логин или пароль';
    header('Location: ../index.php');
    exit;
}

// Если пользователь не авторизован – редирект на логин
if (!isset($_SESSION['token'])) {
    header('Location: ../index.php');
    exit;
}

$token = $_SESSION['token'];
$userData = null;
$updateMessage = '';
$updateError = '';

// Получение данных пользователя
function getUserData($token) {
    $ch = curl_init('https://slqa.ru/pr/api/user/');
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_HTTPHEADER, ['Authorization: Bearer ' . $token]);
    $response = curl_exec($ch);
    $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
    if ($httpCode === 200) {
        $data = json_decode($response, true);
        return $data['user'] ?? null;
    }
    return null;
}

// === ОБРАБОТКА ОБНОВЛЕНИЯ ПРОФИЛЯ ===
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['_method']) && $_POST['_method'] === 'PUT') {
    $updateData = [];
    if (!empty($_POST['email'])) {
        $updateData['email'] = $_POST['email'];
    }
    if (!empty($_POST['username'])) {
        $updateData['username'] = $_POST['username'];
    }
    if (!empty($_POST['new_password'])) { // ← изменено с password на new_password
        $updateData['password'] = $_POST['new_password'];
    }

    if (!empty($updateData)) {
        $ch = curl_init('https://slqa.ru/pr/api/user/');
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_CUSTOMREQUEST, 'PUT');
        curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($updateData));
        curl_setopt($ch, CURLOPT_HTTPHEADER, [
            'Content-Type: application/json',
            'Authorization: Bearer ' . $token
        ]);
        $response = curl_exec($ch);
        $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        curl_close($ch);

        if ($httpCode === 200) {
            $updateMessage = 'Данные обновлены успешно!';
            $userData = getUserData($token); // обновляем данные
        } else {
            $errorData = json_decode($response, true);
            $updateError = $errorData['error'] ?? 'Ошибка обновления данных';
        }
    } else {
        $updateError = 'Нет данных для обновления';
    }
}

// Загрузка данных пользователя
$userData = getUserData($token);
if ($userData === null) {
    session_destroy();
    header('Location: ../index.php');
    exit;
}
?>
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Профиль</title>
    <link rel="stylesheet" href="/pr/assets/css/style.css">
</head>
<body>
    <div class="container">
        <div class="box">
            <h1>👤 Профиль</h1>
            <div class="info">
                <p><strong>ID:</strong> <?= htmlspecialchars($userData['id'] ?? '') ?></p>
                <p><strong>Логин:</strong> <?= htmlspecialchars($userData['username'] ?? '') ?></p>
                <p><strong>Email:</strong> <?= htmlspecialchars($userData['email'] ?? '') ?></p>
                <p><strong>Дата регистрации:</strong> <?= htmlspecialchars($userData['created_at'] ?? '') ?></p>
            </div>
            <h2>Редактировать профиль</h2>
            <?php if ($updateMessage): ?>
                <div class="message"><?= htmlspecialchars($updateMessage) ?></div>
            <?php endif; ?>
            <?php if ($updateError): ?>
                <div class="error"><?= htmlspecialchars($updateError) ?></div>
            <?php endif; ?>
            <form method="POST">
                <input type="hidden" name="_method" value="PUT">
                <label for="username">Логин:</label>
                <input type="text" id="username" name="username" value="<?= htmlspecialchars($userData['username'] ?? '') ?>">
                <label for="email">Email:</label>
                <input type="email" id="email" name="email" value="<?= htmlspecialchars($userData['email'] ?? '') ?>">
                <label for="new_password">Новый пароль:</label>
                <input type="password" id="new_password" name="new_password" autocomplete="new-password" placeholder="Оставьте пустым, если не хотите менять">
                <div class="buttons">
                    <button type="submit">Сохранить</button>
                    <a href="logout.php" class="logout-link">Выйти</a>
                </div>
            </form>
        </div>
    </div>
</body>
</html>