# AuRoom web / Telegram Mini App

React-клиент AuRoom для web и Telegram Mini App.

## Пользовательские разделы

- **Главная** — проекты пользователя;
- **Идеи** — опубликованные визуальные референсы из БД;
- **Создать** — планировка, фасад, мастер-план участка, интерьер;
- **История** — серверная история генераций с cursor pagination;
- **Профиль** — баланс кредитов, тарифы и платежи YooKassa.

Пользователи с ролью `admin`/`superadmin` получают доступ к **Веб-админке**.

## Генерации

Frontend использует реальный Generation API:

- `floor_plan` и `master_plan` поддерживают text-to-image без обязательного исходника;
- `facade` и `interior` требуют reference image;
- стоимость каждого сценария задаётся в webadmin и списывается через credit ledger;
- при техническом падении генерации зарезервированные кредиты возвращаются;
- primary/fallback Nexus-модели и prompt templates управляются из webadmin.

Demo/sandbox generation в production-клиенте не используется.

## Billing

Профиль получает тарифы из backend. YooKassa payment создаётся сервером. При включённой фискализации frontend запрашивает email для чека. Secret key и другие credentials никогда не попадают в frontend.

## Webadmin

Оператор управляет через UI:

- тарифами и фискальными настройками YooKassa;
- стоимостью генераций, AI-моделями, параметрами и prompt templates;
- Ideas и их изображениями;
- пользователями и credit ledger;
- платежами, reconciliation и полным refund;
- Telegram-рассылками, сегментами, scheduling/cancel/retry;
- rate limits, media retention и backup policy;
- audit log.

## Development

```bash
cp .env.example .env
npm install
npm run dev
```

## Проверка

```bash
npm run typecheck
npm run build
```

`VITE_API_BASE_URL` по умолчанию `/api/v1`.

## Telegram Mini App

`index.html` подключает официальный `telegram-web-app.js`. При наличии `window.Telegram.WebApp.initData` приложение автоматически выполняет Telegram auth через backend.
