<?php
// api/login.php - Эндпоинт для авторизации

header('Content-Type: application/json');

require_once __DIR__ . '/../config/database.php';
require_once __DIR__ . '/../src/models/UserModel.php';

try {
    // Создаём модель пользователя
    $userModel = new UserModel($pdo);

    // Получаем данные из запроса
    $inputData = json_decode(file_get_contents('php://input'), true);
    if (!$inputData || !isset($inputData['username']) || !isset($inputData['password'])) {
        http_response_code(400);
        echo json_encode(['error' => 'Необходимо отправить JSON с полями username и password']);
        exit;
    }

    $username = $inputData['username'];
    $password = $inputData['password'];

    // Ищем пользователя
    $user = $userModel->findByUsername($username);

    // Проверяем пароль
    if ($user && password_verify($password, $user['password_hash'])) {
        $token = bin2hex(random_bytes(32));
        
        // Сохраняем токен
        $userModel->saveToken($user['id'], $token);
        
        http_response_code(200);
        echo json_encode([
            'success' => true,
            'token' => $token,
            'message' => 'Авторизация успешна. Токен действует 30 дней.'
        ]);
    } else {
        http_response_code(401);
        echo json_encode(['error' => 'Неверный логин или пароль']);
    }
} catch (Exception $e) {
    http_response_code(500);
    echo json_encode(['error' => $e->getMessage()]);
}