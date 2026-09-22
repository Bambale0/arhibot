# Production-инструкция по верстке фронта AuRoom

Этот документ задает обязательный стандарт production-верстки для фронтенда AuRoom. Он применяется к React/Vite клиенту, Telegram Mini App, пользовательским экранам, questionnaire workspace, просмотру результатов, billing/profile и web-admin.

Цель верстки в production - не просто «красиво выглядит». Экран считается готовым только тогда, когда он устойчиво работает с реальными backend-данными, длинным русским текстом, медленными API, ошибками, пустыми состояниями, мобильным WebView Telegram, клавиатурой, safe-area, admin-операциями и минимальными поддерживаемыми ширинами.

## Контекст продукта

AuRoom - архитектурный AI-продукт. Интерфейс должен ощущаться как цифровой инструмент премиальной архитектурной студии: темные презентационные поверхности, теплое золото как технический акцент, высокая контрастность, точная сетка, спокойная плотность и отсутствие случайного декора.

Production UI не должен выглядеть как:

- generic SaaS dashboard;
- декоративный landing page внутри приложения;
- демо-макет без реальных состояний;
- набор одинаковых карточек ради визуального объема;
- интерфейс, собранный вокруг placeholder-данных.

Текущий фронтенд:

- React 19 + Vite;
- TypeScript;
- plain CSS в `frontend/src/`;
- Telegram Mini App через официальный `telegram-web-app.js`;
- Playwright E2E в `frontend/tests/e2e/`.

## Источники правды

Перед любой версткой нужно свериться с текущими источниками:

- бренд: `docs/brand.md`;
- UX опросника: `docs/questionnaire-ux.md`;
- структура фронта и разделов: `frontend/README.md`;
- app shell и маршрутизация: `frontend/src/App.tsx`, `frontend/src/components/AppFrame.tsx`;
- глобальные и брендовые стили: `frontend/src/styles.css`, `frontend/src/brand.css`, `frontend/src/auroom.css`;
- feature-стили: `frontend/src/questionnaire.css`, `frontend/src/create-questionnaire.css`, `frontend/src/admin.css`, `frontend/src/billing.css`, `frontend/src/ideas.css`, `frontend/src/telegram-fullscreen.css`;
- брендовые ассеты: `frontend/public/brand/auroom-lockup.webp`, `frontend/public/brand/auroom-symbol.webp`.

Нельзя придумывать новую дизайн-систему, если текущую можно расширить. Новый токен, класс или компонент добавляется только тогда, когда он описывает повторяемый продуктовый смысл.

## Бренд

Использовать только утвержденные брендовые ассеты:

- `frontend/public/brand/auroom-lockup.webp` - для splash/loading и крупных брендовых моментов;
- `frontend/public/brand/auroom-symbol.webp` - для компактного знака в UI.

Нельзя перерисовывать куб CSS-фигурами, SVG, emoji, иконками или похожими заменителями.

Основная палитра:

- `#030807` - brand black;
- `#0A1012` - soft black;
- `#E4C67E` - gold;
- `#F1D385` - strong gold highlight;
- `#C99F51` - deep gold;
- `#F5F0E3` - warm ivory text;
- `#A89F8D` - muted warm neutral.

Золото - единственный основной акцент. Нельзя добавлять в основные поверхности случайные синие, зеленые, оранжевые, фиолетовые, бежевые или градиентные акцентные системы без явного продуктового решения.

Опросник может использовать свой архитектурный «рабочий лист» только в рамках `docs/questionnaire-ux.md`. Даже там смысл, читаемость и брендовая целостность важнее декоративности.

## Визуальный язык

Интерфейс должен читаться как архитектурная презентационная доска и рабочий инструмент:

- точная сетка;
- тонкие линии там, где они структурируют информацию;
- сильная иерархия через типографику, отступы и состояние;
- спокойные темные поверхности;
- золото как функциональный акцент;
- минимум декоративных элементов;
- осмысленная плотность.

Избегать:

- карточек внутри карточек;
- одинаковых декоративных панелей на каждом блоке;
- gradient/orb/bokeh-фонов ради красоты;
- больших hero-секций в операционном приложении;
- бейджей, eyebrow-лейблов, номеров и разделителей без информационной роли;
- теней на каждом контейнере;
- all-caps как дефолтного стиля;
- эффектов, которые мешают понять, работает ли экран.

На одном экране достаточно одного-двух запоминающихся визуальных решений. Остальное должно быть спокойным и функциональным.

## Layout-подход

Верстка делается mobile-first, затем расширяется на tablet/desktop.

Минимальная поддерживаемая ширина - `320px`. Каждый измененный экран проверяется на:

- `320px`;
- `375px`;
- `390px`;
- `430px`;
- desktop-ширине, обычно `1280px+`.

Базовые правила:

- CSS Grid использовать для page-level структуры и повторяемых списков/сеток.
- Flexbox использовать для inline-групп, toolbars, controls.
- В grid/flex областях с текстом ставить `min-width: 0`.
- Для колонок с сжимаемым содержимым использовать `minmax(0, 1fr)`.
- Для preview/media/viewer/tile задавать стабильный `aspect-ratio`.
- Для читаемых областей использовать `max-width`.
- Для fixed-низа и Telegram использовать `env(safe-area-inset-*)`.
- Не строить layout под один идеальный текст.

Русские заголовки, email, имена проектов, статусы платежей, admin-значения и generated copy могут быть длиннее макета.

## App shell

Пользовательский app shell использует:

- top bar для бренда и контекста пользователя;
- bottom navigation для основных mobile-разделов;
- ограниченные content areas для обычных страниц;
- full-screen/workspace layout для опросника, просмотра результата, admin и media-heavy экранов.

Fixed navigation не должна перекрывать primary action, input, media controls или системные состояния. Если экран доступен с bottom navigation, ему нужен нижний отступ под:

- высоту bottom nav;
- safe-area;
- клавиатуру и focused inputs, если экран содержит формы.

Primary action на mobile должен быть достижим без охоты по экрану. Для длинных flow допускается sticky action area, но она не должна закрывать важный контент.

## Типографика

Текущий интерфейс использует системный sans-serif и serif-заголовки в отдельных архитектурных местах. Сохранять это разделение:

- sans-serif - controls, navigation, metadata, admin tables, forms, operational UI;
- serif - только там, где нужен архитектурный/editorial тон;
- hero-scale шрифт не использовать внутри компактных panels, admin cards, sidebars, modals, toolbars;
- длину строки держать комфортной, обычно до 80 символов;
- не масштабировать font-size через viewport width;
- не использовать отрицательный letter-spacing для компактных UI labels.

Текст интерфейса - sentence case. CTA должен говорить, что произойдет:

- `Сохранить`;
- `Опубликовать`;
- `Отменить`;
- `Повторить`;
- `Создать проект`;
- `Вернуться к проекту`.

Название действия должно совпадать в кнопке, статусе, toast/inline-сообщении и error recovery.

## Компоненты

Использовать привычные controls:

- button - для явных команд;
- icon button - для компактных инструментов;
- segmented control - для выбора режима;
- radio/checkbox/toggle - для бинарных или множественных выборов;
- slider/stepper/numeric input - для числовых значений;
- tabs - для взаимоисключающих views;
- table/dense list - для admin-операций;
- cards - только для повторяемых items, modals и действительно framed tools.

Не делать «скругленный прямоугольник с текстом» там, где уместнее стандартный control или понятная icon button. Icon-only controls обязаны иметь accessible name.

Карточки не должны содержать unrelated nested cards. Если экрану нужны несколько секций, использовать bands, lists, dividers, grouped layouts или плотные панели без декоративного nesting.

## Обязательные состояния

Каждый API-backed экран обязан иметь:

- loading;
- empty;
- error;
- retry, если восстановление возможно;
- disabled while submitting/loading;
- unauthorized/permission-limited state, где применимо;
- success/complete state, если flow требует подтверждения.

Loading должен сохранять геометрию. Использовать skeleton/reserved dimensions там, где иначе будет скачок.

Empty state должен объяснять, чего нет и что можно сделать. Нельзя заполнять production пустоту fake-проектами, fake-идеями, fake-пользователями, fake-платежами или placeholder-метриками.

Error state должен говорить, что не удалось, и давать путь восстановления. Фраза вроде `Что-то пошло не так` без действия недостаточна.

Disabled state должен быть и визуальным, и программным. Одной opacity недостаточно.

## Формы

Production-форма обязана:

- иметь label для каждого input;
- сохранять visible focus;
- показывать validation рядом с проблемным полем;
- блокировать или защищать submit во время запроса;
- не ломаться от длинных значений;
- не прыгать при появлении ошибок;
- отделять destructive actions;
- давать понятный recovery после ошибки;
- поддерживать keyboard flow.

Long values обрабатывать через wrap, truncate с доступным полным значением или mobile stacking. Нельзя обрезать критичные суммы, статусы, destructive labels и юридически/платежно значимую информацию.

Secrets никогда не показываются в forms, frontend bundles, logs, API responses или admin UI. В admin допустим только безопасный статус вроде `configured: true/false`.

## Данные и конфигурация

Production UI должен получать бизнес-управляемые данные из backend/control plane:

- тарифы, цены, credits;
- public ideas;
- AI model/runtime settings;
- prompt templates;
- broadcasts;
- payment state;
- user operational state;
- Telegram public content and branding;
- rate limits, retention, backup policy.

Нельзя hardcode mutable business configuration в React arrays, CSS, env defaults, prompt constants или conditional branches.

Допустимы только protocol/domain invariants:

- route names;
- enum values;
- API field names;
- validation limits, если они являются контрактом;
- UI constants, которые не являются бизнес-настройкой.

Demo/sandbox behavior должен быть строго development-only и не должен молча попадать в production fallback.

## Web admin

Web admin - control plane, а не витрина. Его верстка должна быть плотной, сканируемой и удобной для повторяемой операторской работы.

Admin UI обязан:

- использовать компактные headings;
- держать filters/search рядом с таблицей или списком;
- показывать loading/empty/error/success/disabled;
- явно выделять destructive actions;
- сохранять audit-контекст там, где он есть;
- не использовать декоративные hero/illustrations;
- не прятать важные operations в hover-only UI;
- оставаться usable на mobile widths, даже если desktop - основной сценарий.

Серверная авторизация обязательна. Скрытая кнопка во frontend не является security boundary.

## Questionnaire UI

Questionnaire - mobile-first архитектурный working sheet, не generic wizard.

Следовать `docs/questionnaire-ux.md`:

- один meaningful question в фокусе;
- wording и business rules источника сохраняются;
- selected states очевидны;
- skip вторичен и показывается только когда разрешен источником;
- custom input очевиден и валидируется до продолжения;
- primary action доступен снизу на mobile;
- selected-object progress не конкурирует с активным вопросом;
- render review - отдельное visual state: сначала image, затем approve/refine;
- safe areas, keyboard, focus-visible и reduced-motion учитываются.

Не загружать heavy 3D/WebGL как часть обычного questionnaire interaction. Heavy media должны появляться только там, где они нужны.

## Media, images, 3D

Для generated previews, history, ideas, media viewer и 3D viewer:

- резервировать размеры до загрузки;
- задавать `aspect-ratio`;
- использовать `object-fit` осознанно;
- не кропать изображение, если пользователь должен его инспектировать;
- показывать понятный missing-media state;
- lazy-load non-critical images;
- не монтировать heavy viewer, если достаточно preview;
- не перекрывать controls/captions важную часть изображения.

Для 3D/WebGL обязательно проверять:

- canvas не пустой;
- объект правильно framed;
- mobile layout не ломается;
- controls доступны;
- viewer не блокирует navigation;
- nonessential animation respects `prefers-reduced-motion`.

## Telegram Mini App

Telegram - production surface, а не «мобильный бонус».

Верстка должна учитывать:

- small widths;
- WebView viewport quirks;
- `env(safe-area-inset-*)`;
- bottom navigation;
- fullscreen button/control;
- virtual keyboard;
- старые Telegram clients без новых fullscreen APIs;
- backend-validated `window.Telegram.WebApp.initData`.

Нельзя доверять `initDataUnsafe` для авторизации. Его можно использовать только для неавторитетных display hints, если backend-контракт это допускает.

Telegram WebApp инициализируется только в client code. Не делать server-side предположений о browser globals.

## Accessibility

Ориентир - WCAG 2.2 AA.

Каждое layout-изменение должно сохранять:

- semantic HTML, где возможно;
- реальные `button` для actions;
- реальные links для navigation, если это навигация;
- visible `:focus-visible`;
- keyboard reachability;
- логичный focus order;
- labels для inputs;
- accessible names для icon-only controls;
- достаточный contrast текста, state borders и focus rings;
- не только цветовое обозначение ошибки/выбора;
- `prefers-reduced-motion` для nonessential motion.

Touch target в основном mobile UI - минимум `44px`. В admin допустима большая плотность, но keyboard/pointer usability должны оставаться понятными.

Не trap-ить focus, кроме modal/dialog. После закрытия modal focus возвращается туда, откуда пользователь пришел.

## Responsive-проверка

На `320px` интерфейс может быть плотнее, но не может быть сломан.

Недопустимо:

- горизонтальный scroll всей страницы, кроме intentional table/media overflow;
- clipping текста внутри кнопок;
- overlapping controls/text;
- bottom nav поверх primary action;
- fixed-width card шире viewport;
- two-column form rows, которые становятся нечитаемыми;
- media controls за пределами viewport;
- invisible focus;
- hover-only действия на mobile.

Лучше перестроить структуру, чем уменьшать шрифт. Stack columns, скрыть вторичную metadata, вынести actions в toolbar или сделать compact icon control с accessible name.

## CSS-архитектура

Сейчас проект использует plain CSS. Поддерживать этот подход:

- reusable tokens - в `brand.css` или локальном feature CSS, если токен feature-specific;
- global element styles - редко и осознанно;
- feature styles - рядом с feature-файлом;
- media queries - рядом с изменяемым блоком, если возможно;
- `prefers-reduced-motion` - для nonessential transitions;
- selectors - без specificity wars;
- broad selectors - избегать, чтобы случайно не рестайлить admin/questionnaire/auth.

Не добавлять CSS framework или component library ради локальной layout-задачи.

Полезные паттерны:

```css
.layout-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
}

.text-cell {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.media-preview {
  aspect-ratio: 16 / 10;
  overflow: hidden;
}
```

Motion использовать экономно. Анимация должна отвечать на действие пользователя или объяснять изменение состояния.

## Copy и локализация

Большая часть production copy - русская. Верстка должна проектироваться под русский текст с самого начала.

Правила:

- не оставлять English placeholder copy в production screens;
- не рассчитывать, что label будет коротким;
- не использовать uppercase как декор;
- писать ошибки конкретно и actionable;
- сохранять одно название действия в рамках flow;
- ellipsis использовать только для вторичной информации;
- критичные суммы, статусы, действия, ошибки и payment text не обрезать.

Если строка приходит с backend, считать, что она может быть длиннее ожидаемого.

## Performance

Верстка не должна ухудшать производительность:

- route-heavy screens lazy-load по существующему `React.lazy` паттерну;
- below-the-fold images lazy-load;
- heavy media/3D viewer монтировать только при необходимости;
- skeleton держать легким;
- не использовать дорогие CSS filters на больших fixed surfaces;
- не добавлять глобальные animations;
- не провоцировать layout thrashing через JS measurement.

Новая верстка не должна незаметно увеличивать provider calls, generation calls, billing calls или media fetches. Если экрану нужны новые данные, API-зависимость должна быть явной.

## Security и privacy

Frontend-верстка не должна ослаблять безопасность:

- не показывать secrets;
- не логировать tokens или Telegram init data;
- не отдавать admin-only данные не-admin пользователям;
- не считать frontend hiding авторизацией;
- не коммитить customer data, реальные платежи, private media, private screenshots;
- редактировать/маскировать чувствительные значения в docs/examples.

## Production review checklist

Перед PR по frontend layout проверить:

- экран использует текущие brand tokens и approved assets;
- экран выглядит как AuRoom, а не generic SaaS;
- все API-backed states реализованы: loading, empty, error, retry, disabled, success где нужен;
- production fake/demo data не добавлены;
- mutable business configuration не hardcoded;
- ширины `320`, `375`, `390`, `430` usable;
- desktop layout usable на целевой ширине;
- bottom nav и safe areas не перекрывают content/actions;
- длинный русский текст, email, имена, цены, статусы не ломают layout;
- keyboard focus видим и идет в логичном порядке;
- icon-only controls имеют accessible names;
- motion respects `prefers-reduced-motion`;
- media имеет стабильные размеры;
- admin actions остаются server-authorized;
- Telegram WebView учтен для Telegram-reachable экранов.

## Обязательные проверки

Для обычных frontend layout changes:

```bash
cd frontend
npm run typecheck
npm run build
```

Для критичных flow или изменений navigation/auth/questionnaire/admin/fullscreen/billing:

```bash
cd frontend
npm run test:e2e
```

Если full E2E слишком широк для изменения, запустить релевантный Playwright spec и явно написать, что пропущено и почему.

Manual responsive verification обязательна для визуальных изменений. Автотесты не доказывают, что production-экран выглядит связно.

## Definition of done

Frontend layout change считается готовым только когда:

- работает с реальными backend-данными;
- все обязательные состояния реализованы;
- mobile и desktop layouts проверены;
- accessibility basics сохранены;
- Telegram constraints учтены для Telegram-reachable screens;
- mutable business configuration и secrets не hardcoded;
- релевантные typecheck/build/E2E checks пройдены или documented blocker объясняет, почему они не запускались;
- финальный отчет содержит changed files, commands, risks и follow-ups.
