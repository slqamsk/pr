<?php
// src/models/UserModel.php
// Содержит все запросы к БД, связанные с пользователями

class UserModel {
    private $pdo;

    public function __construct($pdo) {
        $this->pdo = $pdo;
    }

    // Найти пользователя по логину
    public function findByUsername($username) {
        try {
            $stmt = $this->pdo->prepare("SELECT id, password_hash FROM users WHERE username = ?");
            $stmt->execute([$username]);
            return $stmt->fetch(PDO::FETCH_ASSOC);
        } catch (PDOException $e) {
            throw new Exception('Ошибка поиска пользователя: ' . $e->getMessage());
        }
    }

    // Сохранить токен для пользователя
    public function saveToken($userId, $token, $expiresInDays = 30) {
        try {
            $stmt = $this->pdo->prepare("INSERT INTO api_tokens (user_id, token, expires_at) VALUES (?, ?, DATE_ADD(NOW(), INTERVAL ? DAY))");
            return $stmt->execute([$userId, $token, $expiresInDays]);
        } catch (PDOException $e) {
            throw new Exception('Ошибка сохранения токена: ' . $e->getMessage());
        }
    }

    // Проверить, существует ли токен (для защищённых эндпоинтов)
    public function findToken($token) {
        try {
            $stmt = $this->pdo->prepare("SELECT user_id FROM api_tokens WHERE token = ? AND expires_at > NOW()");
            $stmt->execute([$token]);
            return $stmt->fetch(PDO::FETCH_ASSOC);
        } catch (PDOException $e) {
            throw new Exception('Ошибка проверки токена: ' . $e->getMessage());
        }
    }

    // === НОВЫЕ МЕТОДЫ ===

    // Найти пользователя по ID
    public function findById($id) {
        try {
            $stmt = $this->pdo->prepare("SELECT id, username, email, created_at FROM users WHERE id = ?");
            $stmt->execute([$id]);
            return $stmt->fetch(PDO::FETCH_ASSOC);
        } catch (PDOException $e) {
            throw new Exception('Ошибка поиска пользователя: ' . $e->getMessage());
        }
    }

    // Проверить, занят ли логин
    public function isUsernameTaken($username, $excludeId = null) {
        try {
            $sql = "SELECT id FROM users WHERE username = ?";
            $params = [$username];
            if ($excludeId) {
                $sql .= " AND id != ?";
                $params[] = $excludeId;
            }
            $stmt = $this->pdo->prepare($sql);
            $stmt->execute($params);
            return $stmt->fetch() !== false;
        } catch (PDOException $e) {
            throw new Exception('Ошибка проверки логина: ' . $e->getMessage());
        }
    }

    // Обновить данные пользователя
    public function update($id, $data) {
        try {
            $fields = [];
            $params = [];
            
            // Проверка и обновление username
            if (isset($data['username'])) {
                if (empty($data['username'])) {
                    throw new Exception('Логин не может быть пустым');
                }
                if ($this->isUsernameTaken($data['username'], $id)) {
                    throw new Exception('Логин уже занят');
                }
                $fields[] = "username = ?";
                $params[] = $data['username'];
            }
            
            // Проверка и обновление email
            if (isset($data['email'])) {
                if (!filter_var($data['email'], FILTER_VALIDATE_EMAIL)) {
                    throw new Exception('Неверный формат email');
                }
                $fields[] = "email = ?";
                $params[] = $data['email'];
            }
            
            // Проверка и обновление пароля
            if (isset($data['password'])) {
                $password = $data['password'];
                
                if (empty($password)) {
                    throw new Exception('Пароль не может быть пустым');
                }
                if (strlen($password) < 8) {
                    throw new Exception('Пароль должен содержать минимум 8 символов');
                }
                if (!preg_match('/[A-Z]/', $password)) {
                    throw new Exception('Пароль должен содержать хотя бы одну заглавную букву');
                }
                if (!preg_match('/[0-9]/', $password)) {
                    throw new Exception('Пароль должен содержать хотя бы одну цифру');
                }
                if (!preg_match('/[!@#$%^&*()\-_=+{};:,<.>]/', $password)) {
                    throw new Exception('Пароль должен содержать хотя бы один спецсимвол (!@#$%^&* и т.д.)');
                }
                
                $fields[] = "password_hash = ?";
                $params[] = password_hash($password, PASSWORD_DEFAULT);
            }
            
            if (empty($fields)) {
                return false;
            }
            
            $params[] = $id;
            $sql = "UPDATE users SET " . implode(', ', $fields) . " WHERE id = ?";
            $stmt = $this->pdo->prepare($sql);
            return $stmt->execute($params);
        } catch (Exception $e) {
            throw new Exception($e->getMessage());
        }
    }

    // Получить ID пользователя по токену (обёртка над findToken)
    public function getUserIdByToken($token) {
        $result = $this->findToken($token);
        return $result ? $result['user_id'] : null;
    }
}