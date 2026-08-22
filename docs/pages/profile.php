<?php
// docs/pages/profile.php - Страница профиля пользователя
session_start();

// Если пользователь не авторизован, перенаправляем на логин
if (!isset($_SESSION['token'])) {
    header('Location: ../index.php');
    exit;
}

$token = $_SESSION['token'];
$userData = null;
$updateMessage = '';
$updateError = '';

// Получаем данные пользователя через API
function getUserData($token) {
    $ch = curl_init('https://slqa.ru/pr/api/user/');
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_HTTPHEADER, [
        'Authorization: Bearer ' . $token
    ]);
    
    $response = curl_exec($ch);
    $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
    
    if ($httpCode === 200) {
        $data = json_decode($response, true);
        return $data['user'] ?? null;
    }
    return null;
}

// Обработка обновления профиля
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $updateData = [];
    if (!empty($_POST['email'])) {
        $updateData['email'] = $_POST['email'];
    }
    if (!empty($_POST['username'])) {
        $updateData['username'] = $_POST['username'];
    }
    if (!empty($_POST['password'])) {
        $updateData['password'] = $_POST['password'];
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
            // Обновляем данные пользователя
            $userData = getUserData($token);
        } else {
            $errorData = json_decode($response, true);
            $updateError = $errorData['error'] ?? 'Ошибка обновления данных';
        }
    }
}

// Если данные не загружены, загружаем их
if ($userData === null) {
    $userData = getUserData($token);
    if ($userData === null) {
        // Если токен невалидный — выходим
        session_destroy();
        header('Location: ../index.php');
        exit;
    }
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
                <label for="username">Логин:</label>
                <input type="text" id="username" name="username" value="<?= htmlspecialchars($userData['username'] ?? '') ?>">
                
                <label for="email">Email:</label>
                <input type="email" id="email" name="email" value="<?= htmlspecialchars($userData['email'] ?? '') ?>">
                
                <label for="password">Новый пароль:</label>
                <input type="password" id="password" name="password" placeholder="Оставьте пустым, если не хотите менять">
                
                <div class="buttons">
                    <button type="submit">Сохранить</button>
                    <a href="../index.php" class="logout-link">Выйти</a>
                </div>
            </form>
        </div>
    </div>
</body>
</html>