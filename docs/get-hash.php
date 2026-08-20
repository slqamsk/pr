<?php
// get-hash.php - Генератор хеша пароля (только PHP)

$hash = '';
$password = '';

// Обработка POST-запроса
if ($_SERVER['REQUEST_METHOD'] === 'POST' && !empty($_POST['password'])) {
    $password = $_POST['password'];
    $hash = password_hash($password, PASSWORD_DEFAULT);
}
?>
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Генератор хеша пароля</title>
</head>
<body>
    <h1>Генератор хеша пароля</h1>
    
    <form method="POST">
        <label>Пароль: <input type="text" name="password" value="<?= htmlspecialchars($password) ?>" required></label>
        <button type="submit">Сгенерировать</button>
    </form>
    
    <?php if ($hash): ?>
        <p><b>Хеш:</b><br><code><?= htmlspecialchars($hash) ?></code></p>
    <?php endif; ?>
</body>
</html>