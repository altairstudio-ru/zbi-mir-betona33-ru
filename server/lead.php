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

$leadType = (string)($body['source'] ?? '');
$source = match ($leadType) {
    'hero'  => 'Заявка-расчёт (главный экран)',
    'price' => 'Запрос прайса',
    default => 'Заявка с сайта',
};

// Формируем текст письма (plain text, без user data в заголовках)
$lines = [$source . ' — zhbi.mir-betona33.ru', ''];
foreach ([
    'Телефон'  => $phone,
    'Email'    => $email,
    'Позиция'  => $body['product'] ?? null,
    'Количество' => $body['quantity'] ?? null,
    'Сумма (без доставки)' => $body['total'] ?? null,
    'Условия'  => $body['requirement'] ?? null,
    'Город'    => $body['city'] ?? null,
    'Комментарий' => $body['comment'] ?? null,
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

// ===== Авто-письмо: прайс-лист клиенту (source=price, если оставил email) =====
// Цены синхронизированы с src/data/products.ts (fbsBlocks) — при изменении цен обновлять оба файла.
$priceMail = 'skip';
if ($leadType === 'price' && filter_var($email, FILTER_VALIDATE_EMAIL)) {
    $fbs = [
        ['ФБС 6-6-6',  '580×600×580', 540, 1761], ['ФБС 8-6-6',  '780×600×580', 570, 2283],
        ['ФБС 9-3-3',  '880×300×280', 190,  853], ['ФБС 9-4-3',  '880×400×280', 250,  864],
        ['ФБС 9-5-3',  '880×500×280', 270, 1122], ['ФБС 9-6-3',  '880×600×280', 380, 1316],
        ['ФБС 9-3-6',  '880×300×580', 320, 1319], ['ФБС 9-4-6',  '880×400×580', 480, 1708],
        ['ФБС 9-5-6',  '880×500×580', 540, 2094], ['ФБС 9-6-6',  '880×600×580', 640, 2540],
        ['ФБС 12-3-3', '1180×300×280', 240, 985], ['ФБС 12-3-6', '1180×300×580', 455, 1747],
        ['ФБС 12-4-3', '1180×400×280', 280, 1173], ['ФБС 12-4-6', '1180×400×580', 580, 2318],
        ['ФБС 12-5-3', '1180×500×280', 380, 1423], ['ФБС 12-5-6', '1180×500×580', 790, 2868],
        ['ФБС 12-6-3', '1180×600×280', 460, 1675], ['ФБС 12-6-6', '1180×600×580', 880, 3399],
        ['ФБС 24-3-6', '2380×300×580', 900, 3471], ['ФБС 24-4-6', '2380×400×580', 1200, 4555],
        ['ФБС 24-5-6', '2380×500×580', 1500, 5723], ['ФБС 24-6-6', '2380×600×580', 1800, 6765],
    ];
    $cell = 'padding:7px 12px;border-bottom:1px solid #e2e8f0;font-size:14px;color:#1e293b;';
    $rows = '';
    foreach ($fbs as $i => $r) {
        $bg = $i % 2 ? ' background-color:#f8fafc;' : '';
        $rows .= '<tr>'
            . '<td style="' . $cell . 'font-weight:700;' . $bg . '">' . $r[0] . '</td>'
            . '<td style="' . $cell . $bg . '">' . $r[1] . ' мм</td>'
            . '<td style="' . $cell . 'text-align:right;' . $bg . '">' . number_format($r[2], 0, '', ' ') . ' кг</td>'
            . '<td style="' . $cell . 'text-align:right;font-weight:700;color:#E44D24;white-space:nowrap;' . $bg . '">' . number_format($r[3], 0, '', ' ') . ' ₽</td>'
            . '</tr>';
    }
    $today = date('d.m.Y');
    $html = <<<HTML
<div style="font-family:Arial,Helvetica,sans-serif;background:#eef1f5;padding:24px 8px;">
  <div style="max-width:640px;margin:0 auto;background:#ffffff;border-radius:10px;overflow:hidden;border:1px solid #e2e8f0;">
    <div style="background:#1e293b;color:#ffffff;padding:22px 28px;">
      <div style="font-size:19px;font-weight:800;">МИР БЕТОНА <span style="display:inline-block;background:#E44D24;color:#fff;font-size:12px;font-weight:800;padding:2px 6px;border-radius:4px;vertical-align:middle;">ЖБИ</span></div>
      <div style="font-size:12.5px;opacity:.75;margin-top:4px;">Завод бетонных изделий · 600020, г. Владимир, ул. Большая Нижегородская, д. 71, офис 19А · прайс от $today, действует 14 дней</div>
    </div>
    <div style="padding:24px 28px 8px;">
      <p style="margin:0 0 14px;font-size:15px;color:#1e293b;">Здравствуйте! Как и обещали — актуальные цены на фундаментные блоки (ФБС), руб. за штуку с НДС:</p>
      <table style="width:100%;border-collapse:collapse;">
        <tr>
          <td style="padding:8px 12px;background:#1e293b;color:#fff;font-size:13px;font-weight:700;">Марка</td>
          <td style="padding:8px 12px;background:#1e293b;color:#fff;font-size:13px;font-weight:700;">Размер</td>
          <td style="padding:8px 12px;background:#1e293b;color:#fff;font-size:13px;font-weight:700;text-align:right;">Вес</td>
          <td style="padding:8px 12px;background:#1e293b;color:#fff;font-size:13px;font-weight:700;text-align:right;">Цена</td>
        </tr>
        $rows
      </table>
      <p style="margin:16px 0 0;font-size:13px;color:#64748b;line-height:1.5;">
        Цены без доставки — итоговую смету с логистикой зафиксирует инженер (это бесплатно и ни к чему не обязывает).
        Плиты, кольца, лотки, товарный бетон и нестандартные ЖБИ по чертежам — рассчитаем индивидуально.<br/>
        Версию для печати и сохранения в PDF: <a href="https://zhbi.mir-betona33.ru/price-list/" style="color:#E44D24;">zhbi.mir-betona33.ru/price-list</a>
      </p>
    </div>
    <div style="background:#f8fafc;border-top:1px solid #e2e8f0;padding:18px 28px;font-size:14px;color:#1e293b;">
      <b>Отдел продаж:</b><br/>
      <a href="tel:+74922604933" style="color:#1e293b;text-decoration:none;">+7 (4922) 60-49-33</a> ·
      <a href="tel:+79308304933" style="color:#1e293b;text-decoration:none;">+7 (930) 830-49-33</a> ·
      <a href="mailto:sales@mir-betona33.ru" style="color:#E44D24;text-decoration:none;">sales@mir-betona33.ru</a><br/>
      <span style="font-size:12.5px;color:#64748b;">Пн–Пт 8:00–17:00 · отгрузка 24/7 · паспорт партии на каждую машину</span><br/>
      <span style="font-size:11.5px;color:#94a3b8;">ООО «Мир Бетона 33» · ИНН 3329097979 · КПП 332901001 · ОГРН 1203300003500 · 600020, г. Владимир, ул. Большая Нижегородская, д. 71, офис 19А</span>
    </div>
  </div>
</div>
HTML;
    $mHeaders = implode("\r\n", [
        'From: "МИР БЕТОНА ЖБИ" <' . LEAD_FROM . '>',
        'Reply-To: sales@mir-betona33.ru',
        'Content-Type: text/html; charset=utf-8',
        'Content-Transfer-Encoding: 8bit',
        'X-Mailer: zbi-lead-handler',
    ]);
    $pSubj = '=?UTF-8?B?' . base64_encode('Прайс-лист ФБС — завод «Мир Бетона», Владимир') . '?=';
    $priceMail = @mail($email, $pSubj, $html, $mHeaders) ? 'sent' : 'failed';
}

if (!$sent) {
    http_response_code(502);
    echo json_encode(['ok' => false, 'error' => 'Не удалось отправить, позвоните +7 (4922) 60-49-33 или +7 (930) 830-49-33'], JSON_UNESCAPED_UNICODE);
    exit;
}

echo json_encode([
    'ok' => true,
    'priceMail' => $priceMail, // 'sent' | 'failed' | 'skip' — только для source=price с email
]);
