# AuRoom MVP App

Адаптивный React-клиент для AuRoom: web + Telegram Mini App.

## Основные страницы

- Главная — проекты пользователя;
- Идеи — лента готовых направлений;
- Создать — четыре сценария проектирования;
- История — результаты тестовых генераций в песочнице;
- Профиль — текущий пользователь и управление сессией.

## Сценарии «Создать»

1. Планировка дома;
2. Внешний облик дома / фасад;
3. Мастер-план участка;
4. Дизайн помещений.

## Что подключено к backend

- автоматический Telegram Mini App login через `initData`;
- веб-вход тестового аккаунта без публичной регистрации;
- access + rotating refresh token;
- проекты: список, создание, открытие, архивирование;
- локальная загрузка JPEG / PNG / WebP через `POST /api/v1/assets`;
- удаление загруженного asset.

API берётся из `VITE_API_BASE_URL` и по умолчанию равен `/api/v1`.

## Sandbox generation

Реального `/generations` endpoint и AI-провайдера в текущем backend пока нет. Для проверки полного клиентского flow используется:

```env
VITE_DEMO_GENERATION=true
```

Sandbox явно помечает результат и сохраняет его в локальную «Историю». Он не выдаёт исходное изображение за реальный AI output.

## Development

```bash
cp .env.example .env
npm install
npm run dev
```

## Build

```bash
npm run typecheck
npm run build
```

## Docker

```bash
docker build \
  --build-arg VITE_API_BASE_URL=/api/v1 \
  --build-arg VITE_APP_NAME=AuRoom \
  -t auroom-app .

docker run --rm -p 8080:80 auroom-app
```

## Telegram Mini App

`index.html` подключает официальный `telegram-web-app.js`. При наличии `window.Telegram.WebApp.initData` приложение автоматически вызывает `/api/v1/auth/telegram`.

## Рассылка

Рассылка не показывается обычному пользователю. Операторская команда backend отправляет текст всем активным Telegram identity:

```bash
python -m app.telegram_bot.broadcast --text "Сообщение"
python -m app.telegram_bot.broadcast --text "Сообщение" --dry-run
```

## Следующий backend-срез

Нужен Generation API + один реальный AI-провайдер. После этого песочничная история заменяется серверной историей генераций.
