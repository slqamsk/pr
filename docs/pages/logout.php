<?php
// docs/pages/logout.php - Выход из системы
session_start();
session_destroy();
header('Location: ../index.php');
exit;