<?php
echo "<h1>✅ Деплой работает!</h1>";
echo "<p>Время сервера: " . date('Y-m-d H:i:s') . "</p>";
echo "<hr>";
echo "<p>Файлов в папке: " . count(scandir(__DIR__)) - 2 . "</p>";
phpinfo();