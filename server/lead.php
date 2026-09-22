<?php
/**
 * lead.php — обработчик заявок для zhbi.mir-betona33.ru (TimeWeb, nginx+PHP-FPM).
 *
 * Замена serverless-функции api/lead.ts с Vercel. Фронтенд шлёт
 * POST /api/lead с JSON-телом (source: 'hero' | 'price') и ожидает
 * ответ JSON: { ok: true } либо { ok: false, error: "..." }.
 *
 * Заявки отправляются письмом на LEAD_TO через PHP mail().
 * Если mail() на сервере не настроен — см. комментарий про SMTP ниже.
 */

declare(strict_types=1);

// ====== НАСТРОЙКИ ======
const LEAD_TO   = 'sales@mir-betona33.ru'; // куда слать заявки
const LEAD_FROM = 'website@mir-betona33.ru'; // конверт-отправитель (должен быть на домене сервера)
// =======================

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');

if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    http_response_code(405);
    echo json_encode(['ok' => false, 'error' => 'Method not allowed'], JSON_UNESCAPED_UNICODE);
    exit;
}

$raw  = file_get_contents('php://input');
$body = json_decode((string)$raw, true);
if (!is_array($body)) {
    http_response_code(400);
    echo json_encode(['ok' => false, 'error' => 'Некорректный формат данных'], JSON_UNESCAPED_UNICODE);
    exit;
}

$phone = trim((string)($body['phone'] ?? ''));
$email = trim((string)($body['email'] ?? ''));

if ($phone === '' && $email === '') {
    http_response_code(400);
    echo json_encode(['ok' => false, 'error' => 'Укажите телефон или email'], JSON_UNESCAPED_UNICODE);
    exit;
}
if ($phone !== '' && !preg_match('/^\+?[0-9\s\-()]{6,20}$/', $phone)) {
    http_response_code(400);
    echo json_encode(['ok' => false, 'error' => 'Проверьте номер телефона'], JSON_UNESCAPED_UNICODE);
    exit;
}

// Простейшая защита от спама: honeypot-поле + частота не чаще 1 заявки с IP в 10 сек.
if (!empty($body['website'])) {
    echo json_encode(['ok' => true]); // притворяемся успешным, не отправляя
    exit;
}
$lockFile = sys_get_temp_dir() . '/lead_' . md5($_SERVER['REMOTE_ADDR'] ?? 'na') . '.lock';
if (is_file($lockFile) && filemtime($lockFile) > time() - 10) {
    http_response_code(429);
    echo json_encode(['ok' => false, 'error' => 'Слишком часто, подождите немного'], JSON_UNESCAPED_UNICODE);
    exit;
}
@touch($lockFile);

$source = match ((string)($body['source'] ?? '')) {
    'hero'  => 'Заявка-расчёт (главный экран)',
    'price' => 'Запрос прайса',
    default => 'Заявка с сайта',
};

// Формируем текст письма (plain text, без user data в заголовках)
$lines = [$source . ' — zhbi.mir-betona33.ru', ''];
foreach ([
    'Телефон'  => $phone,
    'Email'    => $email,
    'Изделие'  => $body['product'] ?? null,
    'Потребность' => $body['requirement'] ?? null,
    'Город'    => $body['city'] ?? null,
] as $label => $value) {
    $value = trim((string)($value ?? ''));
    if ($value !== '') {
        $lines[] = $label . ': ' . $value;
    }
}
$lines[] = '';
$lines[] = 'IP: ' . ($_SERVER['REMOTE_ADDR'] ?? '-');
$lines[] = 'UA: ' . substr((string)($_SERVER['HTTP_USER_AGENT'] ?? ''), 0, 200);
$lines[] = 'Время: ' . date('Y-m-d H:i:s T');

$subject = 'Новая заявка: ' . ($phone !== '' ? $phone : $email);

// Заголовки:From — только на подконтрольном домене, Reply-To из формы вычищаем
$replyTo = filter_var($email, FILTER_VALIDATE_EMAIL) ? $email : LEAD_FROM;
$headers = implode("\r\n", [
    'From: "ЖБИ сайт" <' . LEAD_FROM . '>',
    'Reply-To: ' . preg_replace('/[^a-zA-Z0-9@.\-_]/', '', $replyTo),
    'Content-Type: text/plain; charset=utf-8',
    'Content-Transfer-Encoding: 8bit',
    'X-Mailer: zbi-lead-handler',
]);

$bodyText = implode("\r\n", $lines);
$sent = @mail(LEAD_TO, '=?UTF-8?B?' . base64_encode($subject) . '?=', $bodyText, $headers);

// always-лог на сервере: даже если письмо не ушло, заявка не потеряется
// (logs/ лежит ВНЕ public_html: ~/zhbi.mir-betona33.ru/logs)
$dir = dirname(__DIR__, 3) . '/logs';
if (!is_dir($dir)) @mkdir($dir, 0755, true);
file_put_contents(
    $dir . '/leads.log',
    date('c') . "\t" . str_replace(["\r", "\n", "\t"], ' ', $bodyText) . "\tsent=" . ($sent ? '1' : '0') . "\n",
    FILE_APPEND | LOCK_EX
);

if (!$sent) {
    http_response_code(502);
    echo json_encode(['ok' => false, 'error' => 'Не удалось отправить, позвоните +7 (4922) 49-48-91'], JSON_UNESCAPED_UNICODE);
    exit;
}

echo json_encode(['ok' => true]);
