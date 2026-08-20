<?php
// api/user.php - Эндпоинт для работы с пользователем

header('Content-Type: application/json');

require_once __DIR__ . '/../config/database.php';
require_once __DIR__ . '/../src/models/UserModel.php';

try {
    $userModel = new UserModel($pdo);

    // Получаем токен (работает на всех хостингах)
    $authHeader = $_SERVER['HTTP_AUTHORIZATION'] ?? $_SERVER['REDIRECT_HTTP_AUTHORIZATION'] ?? '';
    
    if (empty($authHeader) || !preg_match('/Bearer\s(\S+)/', $authHeader, $matches)) {
        http_response_code(401);
        echo json_encode(['error' => 'Токен не предоставлен или неверный формат. Используйте Authorization: Bearer {token}']);
        exit;
    }
    
    $token = $matches[1];
    $userId = $userModel->getUserIdByToken($token);
    
    if (!$userId) {
        http_response_code(401);
        echo json_encode(['error' => 'Недействительный или истёкший токен']);
        exit;
    }

    $method = $_SERVER['REQUEST_METHOD'];

    // GET /api/user/ - получить информацию о пользователе
    if ($method === 'GET') {
        $user = $userModel->findById($userId);
        if ($user) {
            http_response_code(200);
            echo json_encode([
                'success' => true,
                'user' => [
                    'id' => $user['id'],
                    'username' => $user['username'],
                    'email' => $user['email'],
                    'created_at' => $user['created_at']
                ]
            ]);
        } else {
            http_response_code(404);
            echo json_encode(['error' => 'Пользователь не найден']);
        }
    }
    // PUT /api/user/ - обновить информацию о пользователе
    elseif ($method === 'PUT') {
        $inputData = json_decode(file_get_contents('php://input'), true);
        
        if (!$inputData) {
            http_response_code(400);
            echo json_encode(['error' => 'Необходимо отправить JSON с данными для обновления']);
            exit;
        }
        
        if (!isset($inputData['email']) && !isset($inputData['password'])) {
            http_response_code(400);
            echo json_encode(['error' => 'Укажите email или password для обновления']);
            exit;
        }
        
        $updated = $userModel->update($userId, $inputData);
        
        if ($updated) {
            http_response_code(200);
            echo json_encode([
                'success' => true,
                'message' => 'Данные пользователя обновлены'
            ]);
        } else {
            http_response_code(400);
            echo json_encode(['error' => 'Нет данных для обновления']);
        }
    } else {
        http_response_code(405);
        echo json_encode(['error' => 'Метод не разрешён. Используйте GET или PUT.']);
    }
} catch (Exception $e) {
    http_response_code(500);
    echo json_encode(['error' => $e->getMessage()]);
}