const webApp = window.Telegram.WebApp;
webApp.ready();

// Скрываем главную кнопку
webApp.MainButton.hide();

// Обход ngrok warning (если используешь)
fetch(location.href, {
    headers: {
        'ngrok-skip-browser-warning': '69420'
    }
}).catch(() => {});

const userId = webApp.initDataUnsafe.user?.id || 'unknown';
const backendUrl = 'https://fleta-electrometallurgical-repercussively.ngrok-free.dev';  // Замени при смене ngrok

const botUsername = 'testmarket2912bot';  // ← Твой реальный username бота

function switchTab(tabId) {
    document.querySelectorAll('section').forEach(sec => sec.classList.remove('active'));
    document.getElementById(tabId).classList.add('active');

    document.querySelectorAll('nav button').forEach(btn => btn.classList.remove('active'));
    const activeButton = Array.from(document.querySelectorAll('nav button'))
        .find(btn => btn.getAttribute('onclick') === `switchTab('${tabId}')`);
    if (activeButton) activeButton.classList.add('active');
}

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

function generateRefLink() {
    const refLink = `t.me/${botUsername}?start=${userId}`;
    const refElement = document.getElementById('ref-link');
    if (refElement) refElement.innerText = refLink;
}

function shareLink() {
    const refText = document.getElementById('ref-link').innerText || '';
    if (refText) {
        webApp.switchInlineQuery(`Пригласи друга в CS2 Marketplace и получи скин бесплатно! ${refText}`);
    }
}

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
                <img src="${item.image}" alt="${item.name}">
                <div class="item-info">
                    <strong>${item.name}</strong><br>
                    <span class="price">${item.price_stars} ⭐</span>
                </div>
                <button class="btn" onclick="buyItem(${item.id}, ${item.price_stars}, '${item.name.replace(/'/g, "\\'")}')">Купить</button>
            `;
            list.appendChild(div);
        });
    } catch (error) {
        console.error('Error fetching items:', error);
        document.getElementById('items-list').innerHTML = '<p style="color:#ef4444;">Ошибка загрузки</p>';
    }
}

// Главная функция оплаты Stars
async function buyItem(itemId, priceStars, itemName) {
    if (!priceStars || priceStars <= 0) {
        alert('Цена не указана');
        return;
    }

    try {
        const response = await fetch(`${backendUrl}/api/create_invoice`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                item_id: itemId,
                user_id: userId,
                price_stars: priceStars
            })
        });

        if (!response.ok) {
            const err = await response.text();
            throw new Error(err || 'Не удалось создать инвойс');
        }

        const data = await response.json();
        const invoiceLink = data.invoice_link;

        webApp.openInvoice(invoiceLink, (status) => {
            if (status === 'paid') {
                alert('⭐ Оплата прошла успешно! Предмет добавлен в профиль.');
                loadProfile();
            } else if (status === 'failed' || status === 'cancelled') {
                alert('Оплата отменена или не удалась.');
            }
        });
    } catch (error) {
        console.error('Error:', error);
        alert('Ошибка при создании оплаты: ' + error.message);
    }
}

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
fetchItems();
switchTab('landing');