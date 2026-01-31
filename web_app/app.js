async function buyItem(itemId, priceStars, itemName, productId = '', priceRub = 0) {
    if (!priceStars || priceStars <= 0) return alert('Цена не указана');

    const profileResponse = await fetch(`${backendUrl}/api/profile/${userId}`);
    const profileData = await profileResponse.json();

    if (!profileData.trade_link || profileData.trade_link === 'Не привязан') {
        alert('Нельзя купить — сначала привяжите trade link в профиле!');
        switchTab('profile');
        return;
    }

    // Проверка баланса
    let balanceData = { available: 0 };
    try {
        const balanceResponse = await fetch(`${backendUrl}/api/balance`);
        if (balanceResponse.ok) {
            balanceData = await balanceResponse.json();
        } else {
            alert('Ошибка проверки баланса. Попробуйте позже.');
            return;
        }
    } catch (e) {
        alert('Ошибка проверки баланса. Попробуйте позже.');
        return;
    }

    if (balanceData.available < (priceRub * 1.1)) {
        alert('Предмет временно недоступен. Повторите попытку позже.');
        return;
    }

    // НОВАЯ ПРОВЕРКА АКТУАЛЬНОЙ ЦЕНЫ (аналогично trade_link и балансу)
    let freshPriceData = { price_rub: 0, quantity: 0 };
    try {
        const priceResponse = await fetch(`${backendUrl}/api/item_price?product_id=${encodeURIComponent(productId)}`);
        if (!priceResponse.ok) {
            throw new Error('Не удалось получить цену');
        }
        freshPriceData = await priceResponse.json();
    } catch (e) {
        alert('Не удалось проверить актуальную цену. Попробуйте позже.');
        return;
    }

    if (freshPriceData.quantity <= 0) {
        alert('Предмет распродан. Обновляем список...');
        fetchItems();
        return;
    }

    if (freshPriceData.price_rub > priceRub * 1.1) {
        alert('Цена изменилась. Обновляем список...');
        fetchItems();
        return;
    }

    // Если всё ок — создаём инвойс
    try {
        const body = {
            item_id: itemId,
            user_id: userId,
            price_stars: priceStars
        };
        if (productId) body.product_id = productId;

        const response = await fetch(`${backendUrl}/api/create_invoice`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });

        if (!response.ok) {
            // Получаем точное сообщение от сервера (включая кулдаун 429)
            let errMessage = 'Не удалось создать инвойс';
            try {
                const errData = await response.json();
                errMessage = errData.detail || errMessage;
            } catch {
                errMessage = await response.text() || errMessage;
            }
            throw new Error(errMessage);
        }

        const data = await response.json();
        webApp.openInvoice(data.invoice_link, (status) => {
            if (status === 'paid') {
                alert('⭐ Оплата прошла успешно! Ожидайте трейд в течение 5 минут.');
                fetchItems();
                loadProfile();
            } else if (status === 'failed' || status === 'cancelled') {
                alert('Оплата не удалась.');
            }
        });
    } catch (error) {
        console.error('Ошибка оплаты:', error);
        // Показываем точное сообщение от сервера (например, кулдаун)
        alert(error.message || 'Ошибка оплаты');
    }
}