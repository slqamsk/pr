<?php
// api/login.php - Эндпоинт для авторизации

header('Content-Type: application/json');

require_once __DIR__ . '/../config/database.php';
require_once __DIR__ . '/../src/models/UserModel.php';

try {
    $userModel = new UserModel($pdo);

    // Получаем данные из POST-запроса
    $inputData = json_decode(file_get_contents('php://input'), true);
    
    if (!$inputData || !isset($inputData['username']) || !isset($inputData['password'])) {
        http_response_code(400);
        echo json_encode(['error' => 'Необходимо отправить JSON с полями username и password']);
        exit;
    }

    $username = $inputData['username'];
    $password = $inputData['password'];

    // Ищем пользователя в БД
    $user = $userModel->findByUsername($username);

    // Проверяем пароль
    if ($user && password_verify($password, $user['password_hash'])) {
        // Проверяем, есть ли уже активный токен у этого пользователя
        $stmt = $pdo->prepare("SELECT token FROM api_tokens WHERE user_id = ? AND expires_at > NOW()");
        $stmt->execute([$user['id']]);
        $existingToken = $stmt->fetch(PDO::FETCH_ASSOC);

        if ($existingToken) {
            // Токен уже есть — возвращаем его
            http_response_code(200);
            echo json_encode([
                'success' => true,
                'token' => $existingToken['token'],
                'message' => 'Токен уже существует. Используйте его.'
            ]);
            exit;
        }

        // Токена нет — создаём новый
        $token = bin2hex(random_bytes(32));
        
        $stmt = $pdo->prepare("INSERT INTO api_tokens (user_id, token, expires_at) VALUES (?, ?, DATE_ADD(NOW(), INTERVAL 30 DAY))");
        $stmt->execute([$user['id'], $token]);

        http_response_code(200);
        echo json_encode([
            'success' => true,
            'token' => $token,
            'message' => 'Новый токен создан.'
        ]);
    } else {
        http_response_code(401);
        echo json_encode(['error' => 'Неверный логин или пароль']);
    }
} catch (Exception $e) {
    http_response_code(500);
    echo json_encode(['error' => $e->getMessage()]);
}