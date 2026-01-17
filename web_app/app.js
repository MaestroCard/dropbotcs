const webApp = window.Telegram.WebApp;
webApp.ready();

// Скрываем главную кнопку Telegram
webApp.MainButton.hide();

// Обход ngrok warning
fetch(location.href, {
    headers: { 'ngrok-skip-browser-warning': '69420' }
}).catch(() => {});

const userId = webApp.initDataUnsafe.user?.id || 'unknown';
const backendUrl = 'https://fleta-electrometallurgical-repercussively.ngrok-free.dev';  // ← Твой актуальный ngrok

const botUsername = 'testmarket2912bot';

let currentPage = 1;
let hasMore = true;
let isLoading = false;
let searchQuery = '';  // Поисковая строка
let allLoadedItems = [];  // Кэш загруженных предметов

// Переключение вкладок
function switchTab(tabId) {
    document.querySelectorAll('section').forEach(sec => sec.classList.remove('active'));
    document.getElementById(tabId).classList.add('active');

    document.querySelectorAll('nav button').forEach(btn => btn.classList.remove('active'));
    const activeBtn = Array.from(document.querySelectorAll('nav button'))
        .find(btn => btn.getAttribute('onclick') === `switchTab('${tabId}')`);
    if (activeBtn) activeBtn.classList.add('active');

    if (tabId === 'marketplace') {
        if (allLoadedItems.length === 0) {
            currentPage = 1;
            hasMore = true;
            fetchItems();
        } else {
            renderItems(allLoadedItems);
            updateLoadMoreButton();
        }
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

        document.getElementById('steam-profile').innerText = data.steam_profile || 'Не привязан';
        document.getElementById('trade-link').innerText = data.trade_link || 'Не привязан';
    } catch (error) {
        console.error('Error loading profile:', error);
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

// Загрузка предметов (добавляет к существующим)
async function fetchItems() {
    if (isLoading || !hasMore) return;
    isLoading = true;

    try {
        const url = `${backendUrl}/api/items?page=${currentPage}&limit=20`;
        console.log(`[FETCH] Загружаем страницу ${currentPage}: ${url}`);

        const response = await fetch(url, {
            headers: {
                'Accept': 'application/json',
                'ngrok-skip-browser-warning': '69420'
            }
        });

        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const data = await response.json();
        console.log('[FETCH] Полученные данные:', data);

        const newItems = data.items || [];
        totalPages = data.pages || 1;

        allLoadedItems = [...allLoadedItems, ...newItems];

        renderItems(allLoadedItems);

        hasMore = currentPage < totalPages;
        currentPage++;

        updateLoadMoreButton();
    } catch (error) {
        console.error('[FETCH] Ошибка загрузки предметов:', error);
        document.getElementById('items-list').innerHTML += '<p style="color:#ef4444;">Ошибка загрузки предметов</p>';
    } finally {
        isLoading = false;
    }
}

// Фильтрация предметов по поисковой строке (локально)
function filterItems(items) {
    if (!searchQuery.trim()) return items;

    const query = searchQuery.toLowerCase().trim();
    return items.filter(item => {
        return item.name.toLowerCase().includes(query);
    });
}

// Отрисовка предметов
function renderItems(items) {
    const list = document.getElementById('items-list');
    list.innerHTML = '';

    if (items.length === 0) {
        list.innerHTML = '<p style="text-align:center; color:#94a3b8;">Ничего не найдено</p>';
        return;
    }

    items.forEach(item => {
        const div = document.createElement('div');
        div.className = 'item';
        div.innerHTML = `
            <img src="${item.image || 'https://via.placeholder.com/80x60?text=No+Image'}" alt="${item.name}">
            <div class="item-info">
                <strong>${item.name}</strong><br>
                <span class="price">${item.price_stars} ⭐</span>
                <p>В наличии: ${item.quantity || 'много'}</p>
            </div>
            <button class="btn" onclick="buyItem(${item.id}, ${item.price_stars}, '${item.name.replace(/'/g, "\\'")}')">Купить</button>
        `;
        list.appendChild(div);
    });
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
    console.log('[ПОИСК] Запрос:', searchQuery);

    // Очищаем кэш и загружаем первую страницу с новым поиском
    allLoadedItems = [];
    currentPage = 1;
    hasMore = true;
    fetchItems();
}

// Обработчики поиска с отладкой
document.addEventListener('DOMContentLoaded', () => {
    const input = document.getElementById('search-input');
    const button = document.getElementById('search-button');

    if (input) {
        console.log('[ОТЛАДКА] Поле поиска найдено');
        input.addEventListener('keydown', (e) => {
            console.log('[ОТЛАДКА] Клавиша нажата:', e.key);
            if (e.key === 'Enter') {
                e.preventDefault();
                console.log('[ПОИСК] Enter нажат');
                performSearch();
            }
        });
    } else {
        console.error('[ОТЛАДКА] Поле #search-input не найдено!');
    }

    if (button) {
        console.log('[ОТЛАДКА] Кнопка поиска найдена');
        button.addEventListener('click', (e) => {
            e.preventDefault();
            console.log('[ПОИСК] Кнопка "Искать" нажата');
            performSearch();
        });
    } else {
        console.error('[ОТЛАДКА] Кнопка #search-button не найдена!');
    }
});

// Покупка через Stars
async function buyItem(itemId, priceStars, itemName) {
    if (!priceStars || priceStars <= 0) return alert('Цена не указана');

    try {
        const response = await fetch(`${backendUrl}/api/create_invoice`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ item_id: itemId, user_id: userId, price_stars: priceStars })
        });

        if (!response.ok) throw new Error('Не удалось создать инвойс');

        const data = await response.json();
        webApp.openInvoice(data.invoice_link, (status) => {
            if (status === 'paid') {
                alert('⭐ Оплата прошла успешно! Предмет добавлен в профиль.');
                loadProfile();
            } else if (status === 'failed' || status === 'cancelled') {
                alert('Оплата отменена или не удалась.');
            }
        });
    } catch (error) {
        console.error('Ошибка оплаты:', error);
        alert('Ошибка при оплате: ' + error.message);
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
            alert('Steam профиль успешно привязан!');
            loadProfile();
            document.getElementById('profile-input').value = '';
            document.getElementById('trade-input').value = '';
        } else {
            alert('Ошибка при привязке.');
        }
    } catch (error) {
        console.error('Error binding Steam:', error);
        alert('Ошибка сети.');
    }
}

// Инициализация
generateRefLink();
loadProfile();
switchTab('landing');

console.log("Мини-приложение запущено");
console.log("User ID:", userId);
console.log("Backend URL:", backendUrl);