# ArchiAI MVP App

Адаптивный React-клиент для `AI Architecture Backend — MVP core`.

## Что уже подключено к реальному backend

- email login / register;
- автоматический Telegram Mini App login через `initData`;
- access + rotating refresh token;
- список проектов;
- создание проекта;
- открытие workspace проекта;
- локальная загрузка JPEG / PNG / WebP через `POST /api/v1/assets`;
- удаление загруженного asset;
- архивирование / возврат проекта.

API берётся из `VITE_API_BASE_URL` и по умолчанию равен `/api/v1`.

## UX продукта

Основной flow:

1. пользователь входит;
2. создаёт проект;
3. загружает фотографию;
4. выбирает `Фасад / Интерьер / Редизайн`;
5. добавляет пожелания;
6. запускает концепт.

Шаг 6 визуально реализован, но **реального `/generations` endpoint в текущем OpenAPI ещё нет**. Frontend не вызывает AI-провайдера напрямую и не хранит API-ключи.

Для показа UX заказчику можно временно включить:

```env
VITE_DEMO_GENERATION=true
```

Demo-mode явно помечает результат и показывает исходное изображение — он не выдаёт его за AI output.

## Development

```bash
cp .env.example .env
npm install
npm run dev
```

Vite dev-server проксирует `/api` на `http://localhost:8000` (или `VITE_DEV_API_TARGET`).

## Build

```bash
npm run typecheck
npm run build
```

## Docker

```bash
docker build \
  --build-arg VITE_API_BASE_URL=https://api.example.com/api/v1 \
  --build-arg VITE_APP_NAME=ArchiAI \
  -t archiai-app .

docker run --rm -p 8080:80 archiai-app
```

Если frontend и backend стоят за одним reverse proxy, лучше использовать `VITE_API_BASE_URL=/api/v1` — тогда не нужен отдельный CORS-контур.

## Telegram Mini App

`index.html` подключает официальный `telegram-web-app.js`. При наличии `window.Telegram.WebApp.initData` приложение автоматически вызывает текущий backend endpoint `/api/v1/auth/telegram` и дальше работает только с платформенными bearer-токенами.

## Структура

```text
src/
  api.ts                 API + refresh-token rotation on 401
  auth.tsx               auth state + Telegram bootstrap
  components/
    AuthScreen.tsx
    ProjectsScreen.tsx
    ProjectModal.tsx
    WorkspaceScreen.tsx
  types.ts
  styles.css
```

Когда появится Generation API, менять нужно в основном action в `WorkspaceScreen` и добавить методы в `api.ts`; текущий upload/project flow уже останется тем же.
