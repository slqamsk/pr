<?php
// api/login.php - Эндпоинт для авторизации

header('Content-Type: application/json');

// --- !!! КОНФИГУРАЦИЯ (ЗАМЕНИТЕ НА СВОИ ДАННЫЕ) !!! ---
// В реальном проекте пользователей и пароли обычно хранят в БД,
// но для начала сделаем простую проверку "как в базе данных".
// Позже вы сможете заменить эту часть на запрос к вашей таблице users.
$validUsers = [
    'admin' => 'password123',   // Логин => Пароль
    'user' => 'userpass',
];
// -----------------------------------------------------------

// Получаем и декодируем JSON, отправленный в теле запроса
$inputData = json_decode(file_get_contents('php://input'), true);

// Проверяем, что данные пришли и содержат логин и пароль
if (!$inputData || !isset($inputData['username']) || !isset($inputData['password'])) {
    http_response_code(400); // Bad Request
    echo json_encode(['error' => 'Необходимо отправить JSON с полями username и password']);
    exit;
}

$username = $inputData['username'];
$password = $inputData['password'];

// Проверяем, существует ли пользователь и правильный ли пароль
if (isset($validUsers[$username]) && $validUsers[$username] === $password) {
    // Аутентификация успешна! Генерируем токен.
    // ВАЖНО: Это простой пример. Для реального проекта используйте более сложный механизм (например, JWT).
    $token = bin2hex(random_bytes(32)); // Генерируем случайную строку длиной 64 символа

    // ВАЖНО: Здесь вы должны сохранить этот токен в базе данных или в памяти,
    // чтобы потом проверять его при запросах к защищённым эндпоинтам.
    // Например: сохранить в таблице `api_tokens` с привязкой к пользователю и временем истечения.

    http_response_code(200); // OK
    echo json_encode([
        'success' => true,
        'token' => $token,
        'message' => 'Авторизация успешна. Сохраните этот токен для последующих запросов.'
    ]);
} else {
    // Неправильный логин или пароль
    http_response_code(401); // Unauthorized
    echo json_encode(['error' => 'Неверный логин или пароль']);
}
?>