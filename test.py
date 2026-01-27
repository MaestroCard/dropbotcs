def is_valid_trade_link(url: str) -> bool:
    if not url:
        return False

    try:
        from urllib.parse import urlparse, parse_qs, unquote

        # Раскодируем HTML-сущности (&amp; → &)
        url = unquote(url)

        parsed = urlparse(url)

        # Разрешаем www. и без него
        if parsed.hostname not in ('steamcommunity.com', 'www.steamcommunity.com'):
            return False

        if not parsed.path.startswith('/tradeoffer/new/'):
            return False

        params = parse_qs(parsed.query)

        partner = params.get('partner', [None])[0]
        token   = params.get('token',   [None])[0]

        if not partner or not token:
            return False

        if not partner.isdigit():
            return False

        # Token обычно состоит из букв, цифр, _, -, иногда +
        allowed_chars = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-+')
        if not all(c in allowed_chars for c in token):
            return False

        # Можно добавить длину, если хочешь строгость
        # if len(token) < 6 or len(token) > 20:
        #     return False

        return True

    except Exception as e:
        return False

print(is_valid_trade_link("https://steamcommunity.com/tradeoffer/new/?partner=59566827&token=CBl2pinD"))