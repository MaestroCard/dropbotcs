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

// Пинг при открытии WebApp — засчитывает отложенный реферал и логирует IP
if (userId && userId !== 'unknown') {
    fetch(`${window.location.origin}/api/webapp_ping`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId }),
    }).catch(() => {});  // fire-and-forget, ошибки не критичны
}

// Динамический backendUrl на основе текущего домена (работает на Railway, ngrok, localhost)
const backendUrl = window.location.origin; // Например: https://your-project.up.railway.app

const botUsername = 'QuestixMarketBot';

let currentPage = 1;
let hasMore = true;
let isLoading = false;
let searchQuery = '';

// Простая выдача подарка без анимации
async function claimGiftSimple() {
    try {
        const response = await fetch(`${backendUrl}/api/claim_gift/${userId}`, {
            method: 'POST'
        });
        
        if (!response.ok) {
            const errData = await response.json();
            alert(errData.detail || 'Ошибка получения подарка');
            return;
        }
        
        const data = await response.json();
        
        // Показываем результат
        alert(`🎉 Поздравляем!\n\nВы получили: ${data.name}\n\nСкин отправлен в трейд!`);
        
        // Обновляем профиль
        loadProfile();
        
    } catch (error) {
        console.error('Ошибка:', error);
        alert('Ошибка сети. Попробуйте позже.');
    }
}
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

        // Убрано отображение steam_profile
        document.getElementById('trade-link').innerText = data.trade_link || 'Не привязан';
    } catch (error) {
        console.error('Error loading profile:', error);
        document.getElementById('referrals').innerText = 'Ошибка';
        // Убрано обновление steam-profile
        document.getElementById('trade-link').innerText = 'Ошибка';
    }
}

function refreshProfile() {
    loadProfile();
}

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
    if (!refText) return;
    
    const shareText = `Пригласи друга в CS2 Marketplace и получи подарок — случайный скин! ${refText}`;
    
    // Открываем нативный диалог шаринга Telegram с выбором чата
    const shareUrl = `https://t.me/share/url?url=${encodeURIComponent(refText)}&text=${encodeURIComponent('Пригласи друга в CS2 Marketplace и получи подарок — случайный скин CS2! 🎁')}`;
    
    webApp.openTelegramLink(shareUrl);
}

// Загрузка предметов
async function fetchItems() {
    if (isLoading || !hasMore) return;
    isLoading = true;

    try {
        let url = `${backendUrl}/api/items?page=${currentPage}&limit=20&balance_check=true`;
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
                    <img onload="this.style.opacity=1" src="${item.image}" alt="${item.name}" onerror="this.src='https://via.placeholder.com/80x60?text=Item'">
                    <div style="flex: 1;">
                        <h3>${item.name}</h3>
                        <div class="price-container">
                            <span class="price-rub">${item.price_rub_display}₽</span>
                            <span class="price-stars">(${item.price_stars}⭐)</span>
                        </div>
                        <p>В наличии: ${item.quantity || 'много'}</p>
                    </div>
                    ${item.quantity > 0 ? `<button class="btn" onclick="buyItem(${item.id}, ${item.price_stars}, '${item.name.replace(/'/g, "\\'")}', '${item.product_id || item.name}', ${item.price_rub}, ${item.price_rub_display || item.price_rub_base || 0})">Купить</button>` : '<span style="color:#ef4444;">Распродано</span>'}
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

// Выбор способа оплаты
function showPaymentSelector(itemId, priceStars, itemName, productId, priceRub, priceRubDisplay = null) {
    // Создаём модальное окно
    const modal = document.createElement('div');
    modal.id = 'payment-modal';
    modal.style.cssText = `
        position: fixed;
        top: 0; left: 0; right: 0; bottom: 0;
        background: rgba(0,0,0,0.8);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 1000;
    `;
    
    // Используем priceRubDisplay если передан, иначе конвертируем (курс ~92 + наценка 2₽ + комиссия 4.16%)
    const priceRubFormatted = priceRubDisplay || Math.ceil((priceRub / 1000 * 92 + 2) * 1.0416);
    
    modal.innerHTML = `
        <div style="background: #1e293b; padding: 30px; border-radius: 20px; max-width: 320px; text-align: center;">
            <h3 style="margin-bottom: 20px; color: #fbbf24;">Выберите способ оплаты</h3>
            <p style="color: #94a3b8; margin-bottom: 25px; font-size: 14px;">${itemName}</p>
            
            <button id="pay-stars" class="btn" style="width: 100%; margin-bottom: 15px; background: linear-gradient(135deg, #3b82f6, #8b5cf6);">
                ⭐ ${priceStars} Stars
            </button>
            
            <button id="pay-rub" class="btn" style="width: 100%; margin-bottom: 20px; background: linear-gradient(135deg, #10b981, #059669);">
                💳 ${priceRubFormatted}₽ (СБП)
            </button>
            
            <button id="pay-cancel" class="btn" style="width: 100%; background: #475569;">
                Отмена
            </button>
        </div>
    `;
    
    document.body.appendChild(modal);
    
    // Обработчики
    document.getElementById('pay-stars').onclick = () => {
        modal.remove();
        buyItemStars(itemId, priceStars, itemName, productId, priceRub);
    };
    
    document.getElementById('pay-rub').onclick = () => {
        modal.remove();
        console.log('[DEBUG] Pay RUB clicked, priceRubFormatted:', priceRubFormatted);
        buyItemRub(itemId, itemName, productId, priceRubFormatted);
    };
    
    document.getElementById('pay-cancel').onclick = () => {
        modal.remove();
    };
}

// Покупка (точка входа)
async function buyItem(itemId, priceStars, itemName, productId = '', priceRub = 0, priceRubDisplay = null) {
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

    // Проверка актуальной цены
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

    // Показываем выбор способа оплаты
    console.log('[DEBUG] buyItem called, priceRubDisplay:', priceRubDisplay);
    showPaymentSelector(itemId, priceStars, itemName, productId, priceRub, priceRubDisplay);
}

// Оплата Stars
async function buyItemStars(itemId, priceStars, itemName, productId, priceRub) {
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
        alert(error.message || 'Ошибка оплаты');
    }
}

// Оплата рублями через Cardlink (СБП)
async function buyItemRub(itemId, itemName, productId, priceRubDisplay) {
    // Проверяем цену
    if (!priceRubDisplay || priceRubDisplay <= 0) {
        alert('Ошибка: цена не указана. Обновите страницу.');
        return;
    }
    
    try {
        const body = {
            item_id: itemId,
            user_id: userId,
            product_id: productId,
            price_rub_display: parseInt(priceRubDisplay)  // Цена с комиссией (то, что платит пользователь)
        };

        const response = await fetch(`${backendUrl}/api/create_rub_invoice`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });

        if (!response.ok) {
            let errMessage = 'Не удалось создать платёж';
            try {
                const errText = await response.text();
                try {
                    const errData = JSON.parse(errText);
                    errMessage = errData.detail || errText || errMessage;
                } catch {
                    errMessage = errText || errMessage;
                }
            } catch {
                // Не удалось прочитать тело ответа
            }
            throw new Error(errMessage);
        }

        const data = await response.json();
        
        // Открываем страницу оплаты (используем link_page_url с /transfer/)
        // После оплаты Cardlink редиректит на Success URL, который обработает сервер
        const paymentUrl = data.payment_page_url || data.payment_url;
        
        if (!paymentUrl) {
            alert('Ошибка: не получена ссылка на оплату');
            return;
        }
        
        webApp.openLink(paymentUrl);
        
        // Показываем простое сообщение
        alert('Откроется страница оплаты СБП. После оплаты вы получите сообщение о её статусе.');
        
    } catch (error) {
        console.error('Ошибка создания платежа:', error);
        alert(error.message || 'Ошибка создания платежа');
    }
}

// Проверка статуса оплаты Cardlink
async function checkCardlinkPayment(paymentId, itemId) {
    try {
        const response = await fetch(`${backendUrl}/api/check_payment/${paymentId}`);
        const data = await response.json();
        
        if (data.status === 'paid') {
            webApp.showPopup({
                title: '✅ Оплата успешна!',
                message: 'Ваш скин будет отправлен в течение 5 минут.',
                buttons: [{id: 'ok', text: 'OK', type: 'default'}]
            });
            fetchItems();
            loadProfile();
        } else if (data.status === 'pending') {
            webApp.showPopup({
                title: '⏳ Ожидание оплаты',
                message: 'Платёж ещё не получен. Попробуйте проверить позже.',
                buttons: [
                    {id: 'retry', text: 'Проверить снова', type: 'default'},
                    {id: 'close', text: 'Закрыть', type: 'destructive'}
                ]
            }, (buttonId) => {
                if (buttonId === 'retry') {
                    checkCardlinkPayment(paymentId, itemId);
                }
            });
        } else {
            alert('Ошибка проверки платежа: ' + (data.error || 'Неизвестная ошибка'));
        }
    } catch (error) {
        console.error('Ошибка проверки платежа:', error);
        alert('Ошибка проверки статуса платежа');
    }
}

// Привязка Steam (только trade_link, profile — фиксированное значение)
async function bindSteam() {
    const trade = document.getElementById('trade-input').value.trim();

    if (!trade) return alert('Заполните поле trade link!');

    if (!isValidTradeLink(trade)) {
        alert('Неверный формат trade-ссылки!\n\nДолжна быть вида:\nhttps://steamcommunity.com/tradeoffer/new/?partner=XXXX&token=XXXXXX');
        return;
    }

    try {
        const response = await fetch(`${backendUrl}/api/bind/${userId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            // Передаём фиксированное значение для profile, чтобы не сломать БД
            body: JSON.stringify({ profile: "Empty", trade_link: trade })
        });

        if (response.ok) {
            alert('Trade link успешно привязан!');
            loadProfile();
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

// Проверка параметров URL
const urlParams = new URLSearchParams(window.location.search);

// Режим получения подарка
if (urlParams.get('mode') === 'claim_gift') {
    claimGiftSimple();
}

// Возврат после оплаты Cardlink
const paymentStatus = urlParams.get('payment');
if (paymentStatus === 'success') {
    webApp.showPopup({
        title: '✅ Оплата успешна!',
        message: 'Ваш платёж обрабатывается. Скин будет отправлен в течение 5 минут.',
        buttons: [{id: 'ok', text: 'OK', type: 'default'}]
    });
    // Убираем параметр из URL
    window.history.replaceState({}, document.title, window.location.pathname);
} else if (paymentStatus === 'fail') {
    const message = urlParams.get('message') || 'Оплата не завершена. Попробуйте снова.';
    webApp.showPopup({
        title: '❌ Оплата отменена',
        message: decodeURIComponent(message),
        buttons: [{id: 'ok', text: 'OK', type: 'default'}]
    });
    window.history.replaceState({}, document.title, window.location.pathname);
} else if (paymentStatus === 'error') {
    const message = urlParams.get('message') || 'Произошла ошибка при обработке платежа.';
    webApp.showPopup({
        title: '⚠️ Ошибка',
        message: decodeURIComponent(message),
        buttons: [{id: 'ok', text: 'OK', type: 'destructive'}]
    });
    window.history.replaceState({}, document.title, window.location.pathname);
}

console.log("Мини-приложение запущено");
console.log("Версия app.js: 2026-03-14-v28");