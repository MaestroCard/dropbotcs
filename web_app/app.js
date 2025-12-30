const webApp = window.Telegram.WebApp;
webApp.ready();  // Обязательно для корректной работы Web App

// Обход ngrok warning page (если используешь бесплатный ngrok)
fetch(location.href, {
    headers: {
        'ngrok-skip-browser-warning': '69420'
    }
}).catch(() => {});

// ID текущего пользователя
const userId = webApp.initDataUnsafe.user?.id || 'unknown';

// Базовый URL бэкенда (замени, если ngrok сменится или перейдёшь на реальный сервер)
const backendUrl = 'https://fleta-electrometallurgical-repercussively.ngrok-free.dev';

// Правильный username твоего бота (проверь в @BotFather)
const botUsername = 'testmarket2912bot';  // ←←←←← ИЗМЕНИ, ЕСЛИ БОТ ИМЕЕТ ДРУГОЙ USERNAME!!!

// Переключение вкладок + подсветка активной кнопки в навбаре
function switchTab(tabId) {
    // Скрываем все секции
    document.querySelectorAll('section').forEach(sec => sec.classList.remove('active'));
    document.getElementById(tabId).classList.add('active');

    // Подсвечиваем активную кнопку
    document.querySelectorAll('nav button').forEach(btn => btn.classList.remove('active'));
    const activeButton = Array.from(document.querySelectorAll('nav button'))
        .find(btn => btn.getAttribute('onclick') === `switchTab('${tabId}')`);
    if (activeButton) activeButton.classList.add('active');
}

// Загрузка профиля пользователя
async function loadProfile() {
    try {
        const response = await fetch(`${backendUrl}/api/profile/${userId}`);
        if (!response.ok) throw new Error('Profile not found');
        const data = await response.json();

        document.getElementById('referrals').innerText = data.referrals || 0;

        const itemsList = document.getElementById('items');
        itemsList.innerHTML = '';
        (data.items || []).forEach(item => {
            const li = document.createElement('li');
            li.innerText = `${item.name} (получен: ${item.date || 'неизвестно'})`;
            itemsList.appendChild(li);
        });

        document.getElementById('steam-profile').innerText = data.steam_profile || 'Не привязан';
        document.getElementById('trade-link').innerText = data.trade_link || 'Не привязан';
    } catch (error) {
        console.error('Error loading profile:', error);
        document.getElementById('items').innerHTML = '<li>Ошибка загрузки профиля</li>';
    }
}

// Генерация и отображение реферальной ссылки
function generateRefLink() {
    const refLink = `t.me/${botUsername}?start=${userId}`;
    const refElement = document.getElementById('ref-link');
    if (refElement) refElement.innerText = refLink;
}

// Поделиться реферальной ссылкой через inline-режим
function shareLink() {
    const refText = document.getElementById('ref-link').innerText || '';
    if (refText) {
        webApp.switchInlineQuery(`Пригласи друга в CS2 Marketplace и получи скин бесплатно! ${refText}`);
    } else {
        alert('Ссылка ещё не сгенерирована');
    }
}

// Загрузка предметов в маркетплейс
async function fetchItems() {
    try {
        const response = await fetch(`${backendUrl}/api/items`);
        if (!response.ok) throw new Error('Items not loaded');
        const items = await response.json();

        const list = document.getElementById('items-list');
        list.innerHTML = '';
        if (items.length === 0) {
            list.innerHTML = '<p style="text-align:center; color:#94a3b8;">Предметов пока нет</p>';
            return;
        }

        items.forEach(item => {
            const div = document.createElement('div');
            div.className = 'item';
            div.innerHTML = `
                <img src="${item.image || 'https://via.placeholder.com/80x60?text=No+Image'}" alt="${item.name}">
                <div class="item-info">
                    <strong>${item.name}</strong><br>
                    <span class="price">${item.price_stars || item.price || 100} Stars</span>
                </div>
                <button class="btn" onclick="buyItem(${item.id})">Купить</button>
            `;
            list.appendChild(div);
        });
    } catch (error) {
        console.error('Error fetching items:', error);
        document.getElementById('items-list').innerHTML = '<p style="color:#ef4444;">Ошибка загрузки предметов</p>';
    }
}

// Покупка предмета через Telegram Stars
function buyItem(itemId) {
    const price = 100;  // Здесь можно динамически брать из item, когда добавишь поле price_stars

    webApp.openInvoice({
        title: 'Покупка скина CS2',
        description: `Предмет ID: ${itemId}`,
        payload: JSON.stringify({ item_id: itemId, user_id: userId }),
        provider_token: '',  // Пусто для Telegram Stars
        currency: 'XTR',
        prices: [{ label: 'Стоимость предмета', amount: price }]
    }, (status) => {
        if (status === 'paid') {
            alert('Оплата прошла успешно! Предмет будет выдан в ближайшее время.');
            loadProfile();  // Обновляем список предметов
        } else if (status === 'failed') {
            alert('Оплата не удалась. Попробуйте позже.');
        }
    });
}

// Привязка Steam профиля и trade link
async function bindSteam() {
    const profile = document.getElementById('profile-input').value.trim();
    const trade = document.getElementById('trade-input').value.trim();

    if (!profile || !trade) {
        alert('Заполните оба поля!');
        return;
    }

    try {
        const response = await fetch(`${backendUrl}/api/bind/${userId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ profile, trade_link: trade })
        });

        if (response.ok) {
            alert('Steam профиль успешно привязан!');
            loadProfile();
            // Очистка полей
            document.getElementById('profile-input').value = '';
            document.getElementById('trade-input').value = '';
        } else {
            alert('Ошибка при привязке. Проверьте данные.');
        }
    } catch (error) {
        console.error('Error binding Steam:', error);
        alert('Ошибка сети. Проверьте интернет.');
    }
}

// Инициализация при загрузке страницы
generateRefLink();
loadProfile();
fetchItems();
switchTab('landing');  // Открываем лендинг по умолчанию