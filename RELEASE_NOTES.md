# Патч AION 2 CrossOver — исправление зависания на логотипе при запуске · v0.1.0

Первый публичный релиз AION 2 CrossOver Fix для **CrossOver 26.3.0.39832 + NotProton 1.1.3** на Apple Silicon.

В проверенном запуске игра прошла логотип, авторизацию и вход в лобби; игрок подтвердил работающий запуск. Долгая игровая сессия, другие Mac и прирост FPS пока не проверены.

В релизе:

- Исходники узкого обхода проблемного выделения памяти на границе 4 ГиБ.
- Готовый загрузчик Wine в ZIP — собирать его самостоятельно не требуется.
- Установщик с отдельными копиями Wine и профиля AION2.
- Проверка поддерживаемых версий по SHA-256.
- Проверка состояния, откат и повторное включение без пересоздания профиля.
- Русская и английская инструкции, тесты установщика и воспроизводящие Windows-тесты.

**Скачать готовую сборку:** [AION2-CrossOver-Logo-Fix-v0.1.0-macos.zip](https://github.com/ofeyigijoso29-png/AION2-CrossOver-Logo-Fix/releases/download/v0.1.0/AION2-CrossOver-Logo-Fix-v0.1.0-macos.zip).

**Установка:** распакуйте ZIP, закройте AION2 и запустите `install.command`. Нужен Python 3.9+. Сначала прочитайте требования в [инструкции](https://github.com/ofeyigijoso29-png/AION2-CrossOver-Logo-Fix#readme). Игра запускается через Steam для Mac с выбранным NotProton.

**Откат:** закройте игру и выполните `uninstall.command`. Отдельный профиль сохраняется; автоматического объединения с исходным профилем нет.

**Помощь:** Telegram **[@bingobangobong](https://t.me/bingobangobong)** — подскажу и помогу с применением.

ZIP содержит установщик, готовый загрузчик Wine, его исходники и LGPL-лицензию. Проприетарные компоненты CrossOver/Steam/AION2, лицензии на эти программы и личные данные не распространяются.

---

## English

Experimental startup workaround for **CrossOver 26.3.0.39832 + NotProton 1.1.3**, Apple Silicon and native Steam for macOS.

The tested game run reached authentication and lobby, with player confirmation. Long-session stability, other hardware and FPS improvements are unverified.

Download **AION2-CrossOver-Logo-Fix-v0.1.0-macos.zip**, extract, fully close AION2 and run `install.command`. Python 3.9+ is required; the Wine loader is already built. Read the [English requirements and instructions](https://github.com/ofeyigijoso29-png/AION2-CrossOver-Logo-Fix/blob/main/README.en.md) first. Roll back with `uninstall.command`; the isolated profile is retained. Support: **[@bingobangobong](https://t.me/bingobangobong)**.
