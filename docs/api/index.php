<?php
// api/index.php - Главная страница API

// Устанавливаем правильный заголовок для JSON
header('Content-Type: application/json');

// Базовая информация об API
$apiInfo = [
    'name' => 'Моё API',
    'version' => '1.0.0',
    'endpoints' => [
        'GET /api/' => 'Список всех доступных эндпоинтов (этот список)',
        'POST /api/login' => 'Авторизация пользователя. Ожидает JSON: {"username": "логин", "password": "пароль"}. Возвращает токен.',
        // Сюда вы сможете добавить новые эндпоинты позже, например:
        // 'GET /api/users' => 'Получить список пользователей (требуется токен)',
        // 'GET /api/posts' => 'Получить список записей (требуется токен)',
    ],
    'documentation' => 'Для защищённых эндпоинтов передавайте токен в заголовке Authorization: Bearer {ваш_токен}',
    'status' => 'API работает'
];

// Выводим информацию в формате JSON
echo json_encode($apiInfo, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT);
?>