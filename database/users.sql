-- Пароль 'password123' захеширован с помощью стандартной функции PHP password_hash()
INSERT INTO `users` (`username`, `password_hash`, `email`) VALUES
('admin', '$2y$10$YourHashedPasswordHere', 'admin@example.com');