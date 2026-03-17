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

const botUsername = 'QuestixMarketBot';

let currentPage = 1;
let hasMore = true;
let isLoading = false;
let searchQuery = '';

async function startGiftAnimation() {
    // Переключаем вкладку
    switchTab('gift-animation');
    
    const titleEl = document.getElementById('case-title');
    const rollContainer = document.getElementById('case-roll');
    const resultScreen = document.getElementById('result-screen');

    // 1. Показываем загрузку
    titleEl.textContent = 'Загружаем кейс...';
    resultScreen.style.display = 'none';
    rollContainer.innerHTML = '<div style="color:#64748b;padding:20px;">Загрузка...</div>';

    // 2. Параллельно: получаем предметы И выдаём подарок
    let caseItems = [];
    let wonData = null;
    
    try {
        const [itemsResp, claimResp] = await Promise.all([
            fetch(`${backendUrl}/api/gift_items`),
            fetch(`${backendUrl}/api/claim_gift/${userId}`, { method: 'POST' })
        ]);
        
        if (itemsResp.ok) {
            const data = await itemsResp.json();
            caseItems = data.items || [];
        }
        
        if (!claimResp.ok) {
            let errorMsg = 'Ошибка при открытии кейса';
            try {
                const errData = await claimResp.json();
                errorMsg = errData.detail || errorMsg;
            } catch {}
            alert(errorMsg);
            switchTab('profile');
            return;
        }
        wonData = await claimResp.json();
    } catch (e) {
        console.error('Ошибка:', e);
        alert('Ошибка сети. Попробуйте позже.');
        switchTab('profile');
        return;
    }

    // Fallback предметы
    if (caseItems.length === 0) {
        caseItems = [
            { image: 'https://community.akamai.steamstatic.com/economy/image/i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyL6kJ_m-B1Z-ua6bbZrLOmsD2avx-9ytd5lRi67gVNwsDvSwtqqc3iXZg4kCZYjReYLtRbum9XgYuvm5wbWjtgUzCn3iSsf8G81tFEeH9rw', name: 'AK-47' },
            { image: 'https://community.akamai.steamstatic.com/economy/image/i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyLwiYbf_jdk7uW-V6V-Kf2cGFidxOp_pewnF3nhxEt0sGnSzN76dH3GOg9xC8FyEORftRe-x9PuYurq71bW3d8UnjK-0H0YSTpMGQ', name: 'Butterfly' },
            { image: 'https://community.akamai.steamstatic.com/economy/image/i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyL8ypexwjFS4_ega6F_H_OGMWrEwL9JuPh5SjuMlxgmoCm6lob-KT-JbwF1WZEjR-YJskK9k9XiYePltAeNjYlAxSn5j34dvCZstb4LB6Ut-7qX0V8Xkv5_2A', name: 'AWP' },
            { image: 'https://community.akamai.steamstatic.com/economy/image/i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyLhx8bf_Cxk_f23aahvLPWWClicyOl-pK8_Sn_rwE1x5z6AyY6qeXmRb1cgWMNwR7Ff4Bm_m9y0Przq4A3b348Q02yg2QQMyM9M', name: 'M4A4' },
            { image: 'https://community.akamai.steamstatic.com/economy/image/i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGJKz2lu_XsnXwtmkJjSU91dh8bj35VTqVBP4io_frnEVvqf_a6VoIfGSXz7Hlbwg57QwSS_mxhl15jiGyN37c3_GZw91W8BwRflK7EfKsa2sfw', name: 'Case' },
            { image: 'https://community.akamai.steamstatic.com/economy/image/i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu4vx603vRA_Olpfu-TVJ7uK9V6xsLvSEHGaA_uJzsfVhSjuqqhsmsS-MmbD-KDnGOFB1Zc4pEr9OrBm6w9bgM-Pi4wLe34tNnCT3jCxJ53s_6rsBUqQkq63V2wnBZOJo55YdZKHw2FL19Wg', name: 'Gloves' }
        ];
    }

    // 3. Строим ленту: случайные предметы + ВЫИГРЫШНЫЙ в ЦЕНТРЕ + ещё случайные
    titleEl.textContent = 'Открываем кейс...';
    rollContainer.innerHTML = '';
    
    // Сбрасываем анимации
    rollContainer.style.animation = 'none';
    rollContainer.style.transition = 'none';
    rollContainer.style.transform = 'translateX(0)';
    
    // Размеры предмета (ширина + margin*2)
    const itemWidth = 170; // 140px + 15px с каждой стороны
    
    // Создаём ленту: 29 случайных + ВЫИГРЫШНЫЙ + 11 случайных
    let html = '';
    const itemsBeforeWinner = 29;
    const itemsAfterWinner = 11;
    
    // Предметы ДО выигрышного
    for (let i = 0; i < itemsBeforeWinner; i++) {
        const randomItem = caseItems[Math.floor(Math.random() * caseItems.length)];
        html += `<img src="${randomItem.image}" alt="${randomItem.name}" class="roll-item">`;
    }
    
    // ВЫИГРЫШНЫЙ предмет (в ЦЕНТРЕ ленты)
    html += `<img src="${wonData.image}" alt="${wonData.name}" class="roll-item" data-winner="true">`;
    
    // Предметы ПОСЛЕ выигрышного
    for (let i = 0; i < itemsAfterWinner; i++) {
        const randomItem = caseItems[Math.floor(Math.random() * caseItems.length)];
        html += `<img src="${randomItem.image}" alt="${randomItem.name}" class="roll-item">`;
    }
    
    rollContainer.innerHTML = html;

    // 4. Получаем актуальную ширину контейнера ПОСЛЕ рендера
    const caseContainer = document.getElementById('case-container');
    const containerWidth = caseContainer.getBoundingClientRect().width;
    
    // 5. Случайная позиция от -4960px до -4980px для точного попадания под полоску
    const finalPosition = 4960 + Math.floor(Math.random() * 21); // 4960-4980

    // 6. Запускаем анимацию с замедлением
    rollContainer.style.transition = 'transform 6s cubic-bezier(0.1, 0.5, 0.2, 1)';
    rollContainer.style.transform = `translateX(-${finalPosition}px)`;

    // 7. Через 6 секунд показываем результат
    setTimeout(() => {
        titleEl.textContent = '🎉 Выпал скин!';
        
        // Через 300ms подсвечиваем выигрышный скин (после полной остановки)
        setTimeout(() => {
            const winnerEl = rollContainer.querySelector('[data-winner="true"]');
            if (winnerEl) {
                winnerEl.style.boxShadow = '0 0 30px #fbbf24, 0 0 60px #fbbf24';
                winnerEl.style.border = '3px solid #fbbf24';
                winnerEl.style.transform = 'scale(1.1)';
                winnerEl.style.transition = 'all 0.3s ease';
                winnerEl.style.zIndex = '100';
            }
        }, 300);
        
        // Показываем результат с задержкой
        setTimeout(() => {
            titleEl.textContent = '🎉 Ваш подарок!';
            
            resultScreen.innerHTML = `
                <div style="background:#1e293b; border-radius:20px; padding:25px; margin:20px auto; max-width:340px; box-shadow:0 0 60px rgba(251,191,36,0.5); animation:fadeIn 0.5s ease;">
                    <img src="${wonData.image}" style="width:100%; border-radius:16px; margin-bottom:15px; box-shadow:0 15px 35px rgba(0,0,0,0.8); animation:pulse 2s infinite;">
                    <h3 style="margin:10px 0; color:#fbbf24; font-size:20px;">${wonData.name}</h3>
                    <p style="color:#94a3b8; margin:5px 0; font-size:14px;">ID сделки: <code>${wonData.deal_id}</code></p>
                    <p style="color:#4ade80; font-weight:600; margin:10px 0;">✅ Отправлен в трейд!</p>
                    <button class="btn" onclick="switchTab('profile')" style="margin-top:20px; width:100%; background:linear-gradient(135deg, #3b82f6, #8b5cf6);">В профиль</button>
                </div>
            `;
            resultScreen.style.display = 'block';
        }, 800);
    }, 6000);
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
    
    const shareText = `Пригласи друга в CS2 Marketplace и получи кейс со случайным скином! ${refText}`;
    
    // Открываем нативный диалог шаринга Telegram с выбором чата
    const shareUrl = `https://t.me/share/url?url=${encodeURIComponent(refText)}&text=${encodeURIComponent('Пригласи друга в CS2 Marketplace и получи кейс со случайным скином! 🎁')}`;
    
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

// Режим открытия подарочного кейса
if (urlParams.get('mode') === 'claim_gift') {
    startGiftAnimation();
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