<?php
// api/index.php - Единая точка входа для API

// Определяем, какой эндпоинт запросили
$path = $_SERVER['REQUEST_URI'] ?? '';
$method = $_SERVER['REQUEST_METHOD'] ?? 'GET';

// Убираем базовый путь /pr/api/
$basePath = '/pr/api/';
if (strpos($path, $basePath) === 0) {
    $path = substr($path, strlen($basePath));
}
$path = trim($path, '/');

// Устанавливаем заголовок для JSON
header('Content-Type: application/json');

// Маршрутизация
switch ($path) {
    case '':
        // GET /api/ - список эндпоинтов
        if ($method === 'GET') {
            echo json_encode([
                'name' => 'Моё API',
                'version' => '1.0.0',
                'endpoints' => [
                    'GET /api/' => 'Список всех эндпоинтов',
                    'POST /api/login/' => 'Авторизация пользователя',
                ]
            ], JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT);
        } else {
            http_response_code(405);
            echo json_encode(['error' => 'Метод не разрешён. Используйте GET.']);
        }
        break;
        
    case 'login':
        // POST /api/login/ - логин
        if ($method === 'POST') {
            require __DIR__ . '/login.php';
        } else {
            http_response_code(405);
            echo json_encode(['error' => 'Метод не разрешён. Используйте POST.']);
        }
        break;
        
    default:
        http_response_code(404);
        echo json_encode(['error' => 'Эндпоинт не найден']);
        break;
}