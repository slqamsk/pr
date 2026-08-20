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
}