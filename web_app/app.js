// app.js

const webApp = window.Telegram.WebApp;
webApp.ready();

// Скрываем главную кнопку Telegram
webApp.MainButton.hide();

// Обход ngrok warning (если используешь ngrok локально)
fetch(location.href, {
    headers: { 'ngrok-skip-browser-warning': '69420' }
}).catch(() => {});

const userId = webApp.initDataUnsafe.user?.id || 'unknown';

// Динамический backendUrl на основе текущего домена (работает на Railway, ngrok, localhost)
const backendUrl = window.location.origin; // Например: https://your-project.up.railway.app

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

// Функция проверки формата trade-ссылки
function isValidTradeLink(url) {
    if (!url || typeof url !== 'string') return false;

    try {
        const parsed = new URL(url);

        if (parsed.hostname !== 'steamcommunity.com' &&
            parsed.hostname !== 'www.steamcommunity.com') {
            return false;
        }

        if (!parsed.pathname.startsWith('/tradeoffer/new/')) {
            return false;
        }

        const params = new URLSearchParams(parsed.search);

        const partner = params.get('partner');
        const token   = params.get('token');

        if (!partner || !token) {
            console.warn('Нет partner или token в trade-ссылке');
            return false;
        }

        if (!/^\d+$/.test(partner)) {
            console.warn('partner не состоит только из цифр:', partner);
            return false;
        }

        if (!/^[a-zA-Z0-9_-]+$/.test(token)) {
            if (!/^[a-zA-Z0-9_+\-]+$/.test(token)) {
                console.warn('Недопустимые символы в token:', token);
                return false;
            }
        }

        if (token.length < 6 || token.length > 20) {
            console.warn('Странная длина token:', token.length);
        }

        return true;

    } catch (e) {
        console.error('Ошибка парсинга URL:', e);
        return false;
    }
}

// Загрузка профиля
async function loadProfile() {
    try {
        const response = await fetch(`${backendUrl}/api/profile/${userId}`);
        
        if (!response.ok) {
            if (response.status === 404) {
                document.getElementById('profile').innerHTML = `
                    <div class="card" style="text-align:center; padding:30px;">
                        <h2>Аккаунт не активирован</h2>
                        <p style="font-size:16px; margin:20px 0;">
                            Сначала напишите боту команду <strong>/start</strong>
                        </p>
                        <button class="btn" onclick="webApp.close()">Закрыть</button>
                    </div>
                `;
                return;
            }
            throw new Error(`HTTP ${response.status}: ${await response.text()}`);
        }

        const data = await response.json();
        console.log('[PROFILE] Loaded data:', data);

        document.getElementById('referrals').innerText = data.referrals || 0;

        document.getElementById('steam-profile').innerText = data.steam_profile || 'Не привязан';
        document.getElementById('trade-link').innerText = data.trade_link || 'Не привязан';
    } catch (error) {
        console.error('Error loading profile:', error);
        document.getElementById('referrals').innerText = 'Ошибка';
        document.getElementById('steam-profile').innerText = 'Ошибка';
        document.getElementById('trade-link').innerText = 'Ошибка';
    }
}

function refreshProfile() {
    loadProfile();
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
            loadProfile();
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
// Реферальная ссылка
async function generateRefLink() {
    const refElement = document.getElementById('ref-link');
    if (!refElement) return;

    try {
        const response = await fetch(`${backendUrl}/api/profile/${userId}`);
        
        if (!response.ok) {
            if (response.status === 404) {
                refElement.innerText = "Сначала напишите боту /start";
                refElement.style.color = "#ef4444";
                return;
            }
            throw new Error(`HTTP ${response.status}`);
        }

        // Если профиль существует — генерируем нормальную ссылку
        const refLink = `t.me/${botUsername}?start=${userId}`;
        refElement.innerText = refLink;
    } catch (error) {
        console.error('Ошибка при генерации реф-ссылки:', error);
        refElement.innerText = "Ошибка. Напишите /start боту";
        refElement.style.color = "#ef4444";
    }
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
        let url = `${backendUrl}/api/items?page=${currentPage}&limit=20&balance_check=true`;  // ← добавлено
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
            list.innerHTML = '<p style="text-align:center; color:#9ca3af;">Нет предметов</p>';
            hasMore = false;
        } else {
            data.items.forEach(item => {
                const div = document.createElement('div');
                div.className = 'item';
                div.innerHTML = `
                    <img src="${item.image}" alt="${item.name}" onerror="this.src='https://via.placeholder.com/80x60?text=Item'">
                    <div style="flex: 1;">
                        <h3>${item.name}</h3>
                        <div class="price-container">
                            <span class="price">${item.price_stars} ⭐</span>
                            <span class="price-usd">(${item.price_usd}$)</span>
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

// Покупка
async function buyItem(itemId, priceStars, itemName, productId = '') {
    if (!priceStars || priceStars <= 0) return alert('Цена не указана');

    const profileResponse = await fetch(`${backendUrl}/api/profile/${userId}`);
    const profileData = await profileResponse.json();

    if (!profileData.trade_link || profileData.trade_link === 'Не привязан') {
        alert('Нельзя купить — сначала привяжите trade link в профиле!');
        switchTab('profile');
        return;
    }

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
            const err = await response.text();
            throw new Error('Не удалось создать инвойс: ' + err);
        }

        const data = await response.json();
        webApp.openInvoice(data.invoice_link, (status) => {
            if (status === 'paid') {
                alert('⭐ Оплата прошла успешно! Предмет добавлен в профиль.');
                loadProfile();
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

    if (!isValidTradeLink(trade)) {
        alert('Неверный формат trade-ссылки!\n\nДолжна быть вида:\nhttps://steamcommunity.com/tradeoffer/new/?partner=XXXX&token=XXXXXX');
        return;
    }

    try {
        const response = await fetch(`${backendUrl}/api/bind/${userId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ profile, trade_link: trade })
        });

        if (response.ok) {
            alert('Steam успешно привязан!');
            loadProfile();
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