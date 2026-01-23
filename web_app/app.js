// app.js

const webApp = window.Telegram.WebApp;
webApp.ready();

// Скрываем главную кнопку Telegram
webApp.MainButton.hide();

// Обход ngrok warning
fetch(location.href, {
    headers: { 'ngrok-skip-browser-warning': '69420' }
}).catch(() => {});

const userId = webApp.initDataUnsafe.user?.id || 'unknown';
const backendUrl = 'https://fleta-electrometallurgical-repercussively.ngrok-free.dev'; // ← актуальный ngrok

const botUsername = 'bottest2314bot';

let currentPage = 1;
let hasMore = true;
let isLoading = false;
let searchQuery = '';

// Переключение вкладок
function switchTab(tabId) {
    document.querySelectorAll('section').forEach(sec => sec.classList.remove('active'));
    document.getElementById(tabId).classList.add('active');

    document.querySelectorAll('nav button').forEach(btn => btn.classList.remove('active'));
    const activeBtn = Array.from(document.querySelectorAll('nav button'))
        .find(btn => btn.getAttribute('onclick') === `switchTab('${tabId}')`);
    if (activeBtn) activeBtn.classList.add('active');

    if (tabId === 'marketplace') {
        currentPage = 1;
        hasMore = true;
        searchQuery = '';
        document.getElementById('search-input').value = '';
        fetchItems();
    }
}

// Загрузка профиля
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

        // Отображение Steam и Trade link
        document.getElementById('steam-profile').innerText = data.steam_profile || 'Не привязан';
        document.getElementById('trade-link').innerText = data.trade_link || 'Не привязан';

        // Показываем кнопку подарка, если он есть
        const giftSection = document.getElementById('gift-section');
        if (data.has_gift) {
            giftSection.innerHTML = '<button class="btn" onclick="claimGift()">Забрать подарок 🎁</button>';
        } else {
            giftSection.innerHTML = '';
        }
    } catch (error) {
        console.error('Error loading profile:', error);
        document.getElementById('items').innerHTML = '<p style="color:#ef4444;">Ошибка загрузки профиля</p>';
    }
}

// Получение подарка
async function claimGift() {
    try {
        const response = await fetch(`${backendUrl}/api/claim_gift/${userId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        if (response.ok) {
            alert('Подарок успешно забран!');
            loadProfile(); // обновляем профиль
        } else {
            const err = await response.text();
            alert('Ошибка при получении подарка: ' + err);
        }
    } catch (error) {
        console.error('Claim gift error:', error);
        alert('Ошибка сети');
    }
}

// Реферальная ссылка
function generateRefLink() {
    const refLink = `t.me/${botUsername}?start=${userId}`;
    const refElement = document.getElementById('ref-link');
    if (refElement) refElement.innerText = refLink;
}

function shareLink() {
    const refText = document.getElementById('ref-link').innerText || '';
    if (refText) webApp.switchInlineQuery(`Пригласи друга в CS2 Marketplace и получи скин бесплатно! ${refText}`);
}

// Загрузка предметов
async function fetchItems() {
    if (isLoading || !hasMore) return;
    isLoading = true;

    try {
        let url = `${backendUrl}/api/items?page=${currentPage}&limit=20`;
        if (searchQuery.trim()) {
            url += `&search=${encodeURIComponent(searchQuery)}`;
        }
        console.log(`[FETCH] Загружаем: ${url}`);

        const response = await fetch(url, {
            headers: {
                'Accept': 'application/json',
                'ngrok-skip-browser-warning': '69420'
            }
        });

        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const data = await response.json();
        console.log('[FETCH] Данные:', data);

        const list = document.getElementById('items-list');
        if (currentPage === 1) list.innerHTML = '';

        if (!data.items || data.items.length === 0) {
            list.innerHTML = '<p style="text-align:center; color:#94a3b8;">Ничего не найдено</p>';
            hasMore = false;
        } else {
            data.items.forEach(item => {
                const div = document.createElement('div');
                div.className = 'item';
                div.innerHTML = `
                    <img src="${item.image || 'https://via.placeholder.com/80x60?text=No+Image'}" alt="${item.name}">
                    <div class="item-info">
                        <strong>${item.name}</strong>
                        <div class="price-container">
                            <span class="price">${item.price_stars} ⭐</span>
                            <span class="price-usd">≈ $${item.price_usd || '?'}</span>
                        </div>
                        <p>В наличии: ${item.quantity || 'много'}</p>
                    </div>
                    <button class="btn" onclick="buyItem(${item.id}, ${item.price_stars}, '${item.name.replace(/'/g, "\\'")}', '${item.product_id || item.name}')">Купить</button>
                `;
                list.appendChild(div);
            });

            hasMore = currentPage < data.pages;
            currentPage++;
        }

        updateLoadMoreButton();
    } catch (error) {
        console.error('[FETCH] Ошибка:', error);
        document.getElementById('items-list').innerHTML += '<p style="color:#ef4444;">Ошибка загрузки</p>';
    } finally {
        isLoading = false;
    }
}

// Кнопка "Загрузить ещё"
function updateLoadMoreButton() {
    let button = document.getElementById('load-more');
    if (button) button.remove();

    if (hasMore) {
        button = document.createElement('button');
        button.id = 'load-more';
        button.className = 'btn';
        button.style.margin = '20px auto';
        button.style.display = 'block';
        button.innerText = 'Загрузить ещё';
        button.onclick = fetchItems;
        document.getElementById('items-list').appendChild(button);
    }
}

// Поиск по кнопке или Enter
function performSearch() {
    searchQuery = document.getElementById('search-input').value.trim();
    currentPage = 1;
    hasMore = true;
    fetchItems();
}

// Обработчики поиска
document.addEventListener('DOMContentLoaded', () => {
    const input = document.getElementById('search-input');
    const button = document.getElementById('search-button');

    input?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            performSearch();
        }
    });

    button?.addEventListener('click', (e) => {
        e.preventDefault();
        performSearch();
    });
});

// Покупка (теперь с product_id)
async function buyItem(itemId, priceStars, itemName, productId = '') {
    if (!priceStars || priceStars <= 0) return alert('Цена не указана');

    try {
        const body = {
            item_id: itemId,
            user_id: userId,
            price_stars: priceStars
        };
        if (productId) {
            body.product_id = productId;  // ← обязательно для Xpanda
        } else {
            console.warn('[BUY] product_id не найден, fallback на name');
            body.product_id = itemName;
        }

        console.log('[BUY] Отправляемые данные:', body);  // ← отладка в консоль браузера

        const response = await fetch(`${backendUrl}/api/create_invoice`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });

        if (!response.ok) {
            const err = await response.text();
            throw new Error('Не удалось создать инвойс: ' + err);
        }

        const data = await response.json();
        webApp.openInvoice(data.invoice_link, (status) => {
            if (status === 'paid') {
                alert('⭐ Оплата прошла успешно! Предмет добавлен в профиль.');
                loadProfile(); // обновляем профиль
            } else if (status === 'failed' || status === 'cancelled') {
                alert('Оплата не удалась.');
            }
        });
    } catch (error) {
        console.error('Ошибка оплаты:', error);
        alert('Ошибка: ' + error.message);
    }
}

// Привязка Steam
async function bindSteam() {
    const profile = document.getElementById('profile-input').value.trim();
    const trade = document.getElementById('trade-input').value.trim();

    if (!profile || !trade) return alert('Заполните оба поля!');

    try {
        const response = await fetch(`${backendUrl}/api/bind/${userId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ profile, trade_link: trade })
        });

        if (response.ok) {
            alert('Steam успешно привязан!');
            loadProfile(); // обновляем профиль после привязки
            document.getElementById('profile-input').value = '';
            document.getElementById('trade-input').value = '';
        } else {
            const err = await response.text();
            alert('Ошибка привязки: ' + err);
        }
    } catch (error) {
        console.error('Bind error:', error);
        alert('Ошибка сети');
    }
}

// Инициализация
generateRefLink();
loadProfile();
switchTab('landing');

console.log("Мини-приложение запущено");
console.log("Версия app.js: 2026-01-23-v4");
alert("Версия v4 загружена!");