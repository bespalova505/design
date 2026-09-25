# Webflow и переносимость

Переменные Webflow в опубликованном коде представлены обычными CSS custom properties. Например, `--spacing--large` ссылается на `--size--3`. Это работает независимо от Webflow.

| В исходнике | В обычной верстке / React | Ограничение |
| --- | --- | --- |
| Variables | CSS custom properties; JSON для преобразования | Наш JSON не заявлен нативным форматом Figma/DTCG |
| Utility classes | CSS, CSS Modules или utilities | Ограничение "не больше 4 классов" относится к workflow исходника |
| Component properties | Props и варианты компонента | HTML не содержит полную редактируемую модель Webflow |
| `spacing-top`, `spacing-bottom` | Props или `data-*` | Ограничить значения допустимым набором |
| `reverse-split-layout` | Prop `imageFirst` и CSS grid/order | Проверить порядок чтения и мобильную версию |
| Шрифты и headings | CSS-токены | Подключать шрифты под бренд, не все сразу |
| Webflow forms | Форма с labels, валидацией и обработчиком | Backend автоматически не переносится |
| Webflow runtime / interactions | JS для архива; собственная реализация для продукта | Переименование HTML в JSX не является полным переносом |
| Finsweet TOC | Оглавление по заголовкам | Вендорный скрипт нужен при сохранении его реализации |

Для Figma можно завести коллекции примитивов и семантических переменных, а типографику и состояния оформить стилями и компонентами. Файл Figma не создавался. Автоматический импорт требует отдельного преобразователя под выбранный инструмент.

## Минимальный пример

`portable/example.html` использует локальные HTML/CSS. `tokens.css` содержит извлеченные токены с исправлениями H6 и portrait-breakpoint. `base.css` - небольшая самостоятельная адаптация, а не полный порт всех 468 классов.

```html
<link rel="stylesheet" href="tokens.css">
<link rel="stylesheet" href="base.css">
<section class="ds-section">
  <div class="ds-container ds-split">
    <div><h1 class="ds-h1">Заголовок проекта</h1></div>
    <div>Содержимое</div>
  </div>
</section>
```

Сначала выбрать значения для одного изолированного проекта. Полный CSS Webflow содержит глобальные reset-правила и стили HTML-тегов; его импорт в действующий React-проект требует анализа конфликтов.

## Граница выгрузки

Сохранены обнаруженные публичные страницы, подключенные статические файлы и ресурсы CSS. Нативные компоненты редактора, настройки проекта и неопубликованные материалы этим способом не получаются. Для Designer использовать [официальный cloneable](https://webflow.com/made-in-webflow/website/caleb-starter-0f0751feaf5-25d1f52be88fe).

Даже официальный экспорт кода имеет ограничения по серверным возможностям: [Webflow: How do I export my site code?](https://help.webflow.com/hc/en-us/articles/33961386739347-How-do-I-export-my-Webflow-site-code). Здесь выполнен публичный архив, а не официальный экспорт.
