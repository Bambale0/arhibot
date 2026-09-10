# AuRoom web / Telegram Mini App

React-клиент AuRoom для web и Telegram Mini App.

## Пользовательские разделы

- **Главная** — проекты пользователя; проекты, созданные через опросник, продолжаются в том же объектном сценарии;
- **Идеи** — лента принятых работ, которые пользователи сами добавили из стандартного сценария «Создать»; сейчас лента показывает статичные изображения без 3D;
- **Создать** — объектный сценарий по опросникам заказчика: выбор объектов → фото участка или без фото → вопросы → генерация → принятие результата → следующий объект или заявка;
- **История** — серверная история сгенерированных работ с cursor pagination; открытие возвращает в questionnaire-проект, а для старых записей показывает готовый результат без legacy-конструктора сценариев;
- **Профиль** — баланс кредитов, тарифы и платежи YooKassa.

Пользователи с ролью `admin`/`superadmin` получают доступ к **Веб-админке**.

## Генерации

Пользователь не выбирает технический `GenerationMode` вручную. Стандартный сценарий «Создать» строит генерацию из текущего объекта, ответов опросника и принятой сцены:

- для дома с исходным изображением backend использует `facade`;
- для добавления объектов на участок и остальных questionnaire-шагов используется `master_plan`;
- `floor_plan` и `interior` остаются legacy/API-типами и не являются пунктами пользовательского ТЗ;
- стоимость доступных generation types задаётся в webadmin и списывается через credit ledger;
- при техническом падении генерации зарезервированные кредиты возвращаются;
- primary/fallback Nexus-модели и prompt templates управляются из webadmin.

Demo/sandbox generation в production-клиенте не используется.

## Billing

Профиль получает тарифы из backend. YooKassa payment создаётся сервером. При включённой фискализации frontend запрашивает email для чека. Secret key и другие credentials никогда не попадают в frontend.

## Webadmin

Оператор управляет через UI:

- тарифами и фискальными настройками YooKassa;
- стоимостью генераций, AI-моделями, параметрами и prompt templates;
- модерацией и порядком опубликованных пользователями работ в Ideas;
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