// ============================================================
// DevTools Snippet - Omex Broker Order Filler
// ============================================================
// 
// نحوه استفاده:
// 1. مرورگر کارگزاری را باز کنید و لاگین کنید
// 2. F12 را بزنید تا DevTools باز شود
// 3. به تب "Sources" بروید
// 4. در پنل چپ، روی "Snippets" کلیک کنید
// 5. یک Snippet جدید بسازید: "omex-filler"
// 6. این کد را paste کنید
// 7. Ctrl+Enter بزنید تا اجرا شود
// 
// پس از اجرا، Snippet هر ۱ ثانیه سرور را poll می‌کند
// و اگر سفارش جدیدی باشد، فرم را پر می‌کند.
// 
// برای توقف:
//   window.__omexSnippetStop__()
// ============================================================

(function () {
    'use strict';

    // ═══════════════════════════════════════════════════════════
    // جلوگیری از اجرای چندباره
    // ═══════════════════════════════════════════════════════════

    if (window.__omexSnippetActive__) {
        console.warn('[OmexSnippet] Already running. Stopping old instance...');
        if (window.__omexSnippetStop__) {
            window.__omexSnippetStop__();
        }
    }

    // ═══════════════════════════════════════════════════════════
    // تنظیمات
    // ═══════════════════════════════════════════════════════════

    const CONFIG = {
        BRIDGE_URL: 'http://127.0.0.1:8000',
        POLL_INTERVAL_MS: 1000,
        HIGHLIGHT_DURATION_MS: 12000,
        ENABLE_SOUND: true,
        ENABLE_NOTIFICATION: true,
        SHOW_BANNER: true,
        LEG_FILL_DELAY_MS: 800,
        ROW_ADD_DELAY_MS: 1200,
    };

    // ═══════════════════════════════════════════════════════════
    // State
    // ═══════════════════════════════════════════════════════════

    let lastOrderId = null;
    let pollTimer = null;
    let isProcessing = false;

    window.__omexSnippetActive__ = true;

    // ═══════════════════════════════════════════════════════════
    // استایل‌ها
    // ═══════════════════════════════════════════════════════════

    function injectStyles() {
        const old = document.getElementById('__omex_snippet_styles__');
        if (old) old.remove();

        const style = document.createElement('style');
        style.id = '__omex_snippet_styles__';
        style.textContent = `
            .omex-snippet-highlight {
                border: 3px solid #00ff00 !important;
                box-shadow: 0 0 15px #00ff00 !important;
                background-color: #f0fff0 !important;
                transition: all 0.2s ease;
            }
            #omex-snippet-banner {
                position: fixed;
                top: 15px;
                right: 15px;
                min-width: 340px;
                max-width: 500px;
                background: linear-gradient(135deg, #1a4d2e, #2d6a4f);
                color: white;
                padding: 18px 24px;
                border-radius: 12px;
                z-index: 2147483647;
                font-family: Tahoma, Arial, sans-serif;
                direction: rtl;
                font-size: 14px;
                box-shadow: 0 8px 24px rgba(0,0,0,0.5);
                display: none;
                border: 2px solid #52b788;
            }
            #omex-snippet-banner.show {
                display: block;
                animation: omexSlideIn 0.3s ease;
            }
            @keyframes omexSlideIn {
                from { transform: translateX(400px); opacity: 0; }
                to { transform: translateX(0); opacity: 1; }
            }
            #omex-snippet-banner h3 {
                margin: 0 0 10px 0;
                color: #b7e4c7;
                font-size: 16px;
                border-bottom: 1px solid #40916c;
                padding-bottom: 8px;
            }
            #omex-snippet-banner .legs-container {
                background: rgba(0,0,0,0.2);
                border-radius: 6px;
                padding: 8px 12px;
                margin: 8px 0;
                font-family: monospace;
                font-size: 12px;
                line-height: 1.8;
                max-height: 200px;
                overflow-y: auto;
            }
            #omex-snippet-banner .leg-row {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 4px 0;
                border-bottom: 1px solid rgba(255,255,255,0.1);
            }
            #omex-snippet-banner .leg-row:last-child {
                border-bottom: none;
            }
            #omex-snippet-banner button {
                margin: 8px 4px 0 0;
                padding: 10px 20px;
                background: #52b788;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                cursor: pointer;
                font-family: Tahoma;
                font-size: 13px;
                font-weight: bold;
                transition: background 0.2s;
            }
            #omex-snippet-banner button:hover {
                background: #40916c;
            }
            #omex-snippet-banner button.skip-btn {
                background: #6c757d;
            }
            #omex-snippet-banner button.skip-btn:hover {
                background: #495057;
            }
            #omex-snippet-banner .status-box {
                margin: 10px 0;
                padding: 8px 12px;
                background: rgba(255,255,255,0.1);
                border-radius: 6px;
                font-size: 12px;
                text-align: center;
                display: none;
            }
            #omex-snippet-banner .status-box.show {
                display: block;
            }
            #omex-snippet-status {
                position: fixed;
                bottom: 8px;
                left: 8px;
                background: rgba(0,0,0,0.75);
                color: #00ff88;
                padding: 5px 10px;
                border-radius: 4px;
                font-family: monospace;
                font-size: 11px;
                z-index: 2147483646;
                pointer-events: none;
            }
        `;
        document.head.appendChild(style);
    }

    // ═══════════════════════════════════════════════════════════
    // بنر هشدار
    // ═══════════════════════════════════════════════════════════

    function createBanner() {
        const old = document.getElementById('omex-snippet-banner');
        if (old) old.remove();

        const banner = document.createElement('div');
        banner.id = 'omex-snippet-banner';
        document.body.appendChild(banner);
        return banner;
    }

    function showBanner(html) {
        const banner = createBanner();
        banner.innerHTML = html;
        banner.classList.add('show');
        return banner;
    }

    function hideBanner() {
        const banner = document.getElementById('omex-snippet-banner');
        if (banner) {
            banner.classList.remove('show');
        }
    }

    function setBannerStatus(text, type) {
        const statusBox = document.querySelector('#omex-snippet-banner .status-box');
        if (!statusBox) return;

        statusBox.classList.add('show');
        statusBox.textContent = text;

        if (type === 'success') {
            statusBox.style.background = 'rgba(76, 175, 80, 0.3)';
        } else if (type === 'error') {
            statusBox.style.background = 'rgba(244, 67, 54, 0.3)';
        } else if (type === 'warning') {
            statusBox.style.background = 'rgba(255, 152, 0, 0.3)';
        } else {
            statusBox.style.background = 'rgba(255,255,255,0.1)';
        }
    }

    // ═══════════════════════════════════════════════════════════
    // Status Bar (کوچک)
    // ═══════════════════════════════════════════════════════════

    function updateStatusBar(text) {
        let statusEl = document.getElementById('omex-snippet-status');
        if (!statusEl) {
            statusEl = document.createElement('div');
            statusEl.id = 'omex-snippet-status';
            document.body.appendChild(statusEl);
        }
        statusEl.textContent = text;
    }

    // ═══════════════════════════════════════════════════════════
    // Notification API
    // ═══════════════════════════════════════════════════════════

    function notify(title, body) {
        if (!CONFIG.ENABLE_NOTIFICATION) return;
        if (!('Notification' in window)) return;

        if (Notification.permission === 'granted') {
            new Notification(title, { body: body, icon: '' });
        } else if (Notification.permission !== 'denied') {
            Notification.requestPermission().then(function (permission) {
                if (permission === 'granted') {
                    new Notification(title, { body: body, icon: '' });
                }
            });
        }
    }

    // ═══════════════════════════════════════════════════════════
    // صدا
    // ═══════════════════════════════════════════════════════════

    function playBeep() {
        if (!CONFIG.ENABLE_SOUND) return;
        try {
            const AudioCtx = window.AudioContext || window.webkitAudioContext;
            const ctx = new AudioCtx();
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.frequency.value = 880;
            gain.gain.setValueAtTime(0.3, ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.4);
            osc.start();
            osc.stop(ctx.currentTime + 0.4);
        } catch (e) {
            // silent
        }
    }

    // ═══════════════════════════════════════════════════════════
    // پیدا کردن فیلد
    // ═══════════════════════════════════════════════════════════

    function findField(labels, root) {
        root = root || document;

        // روش ۱: label[for] → input
        const labelElements = root.querySelectorAll('label');
        for (let i = 0; i < labelElements.length; i++) {
            const lbl = labelElements[i];
            const txt = (lbl.textContent || '').trim();
            if (!txt) continue;

            for (let j = 0; j < labels.length; j++) {
                if (txt.indexOf(labels[j]) !== -1) {
                    const forId = lbl.getAttribute('for');
                    if (forId) {
                        const el = document.getElementById(forId);
                        if (el) return el;
                    }
                    const parent = lbl.parentElement;
                    if (parent) {
                        const sib = parent.querySelector('input, select, textarea');
                        if (sib) return sib;
                    }
                }
            }
        }

        // روش ۲: جدول‌ها (کارگزاری‌های ایرانی)
        const cells = root.querySelectorAll('td, th, div, span');
        for (let i = 0; i < cells.length; i++) {
            const cell = cells[i];
            const txt = (cell.textContent || '').trim();
            if (txt.length > 30) continue;

            for (let j = 0; j < labels.length; j++) {
                if (txt === labels[j] || txt.indexOf(labels[j]) !== -1) {
                    const container = cell.closest('tr, .form-group, .row') ||
                        cell.parentElement;
                    if (container) {
                        const inp = container.querySelector(
                            'input:not([type="hidden"]), select, textarea'
                        );
                        if (inp) return inp;
                    }
                }
            }
        }

        // روش ۳: name/id/placeholder
        const inputs = root.querySelectorAll(
            'input:not([type="hidden"]), select, textarea'
        );
        for (let i = 0; i < inputs.length; i++) {
            const inp = inputs[i];
            const attrs = [
                inp.name, inp.id, inp.placeholder,
                inp.getAttribute('aria-label'),
                inp.getAttribute('formcontrolname')
            ].filter(Boolean).join(' ').toLowerCase();

            for (let j = 0; j < labels.length; j++) {
                if (attrs.indexOf(labels[j].toLowerCase()) !== -1) {
                    return inp;
                }
            }
        }

        return null;
    }

    // ═══════════════════════════════════════════════════════════
    // پر کردن فیلد (سازگار با React/Vue/Angular)
    // ═══════════════════════════════════════════════════════════

    function fillField(input, value) {
        if (!input) return false;

        try {
            let proto;
            if (input.tagName === 'SELECT') {
                proto = window.HTMLSelectElement.prototype;
            } else if (input.tagName === 'TEXTAREA') {
                proto = window.HTMLTextAreaElement.prototype;
            } else {
                proto = window.HTMLInputElement.prototype;
            }

            const setter = Object.getOwnPropertyDescriptor(proto, 'value');
            if (setter && setter.set) {
                setter.set.call(input, String(value));
            } else {
                input.value = String(value);
            }

            ['input', 'change', 'blur', 'keyup'].forEach(function (evt) {
                input.dispatchEvent(new Event(evt, { bubbles: true }));
            });

            // هایلایت موقت
            input.classList.add('omex-snippet-highlight');
            setTimeout(function () {
                input.classList.remove('omex-snippet-highlight');
            }, CONFIG.HIGHLIGHT_DURATION_MS);

            return true;
        } catch (e) {
            console.error('[OmexSnippet] fillField error:', e);
            return false;
        }
    }

    // ═══════════════════════════════════════════════════════════
    // پر کردن یک لگ
    // ═══════════════════════════════════════════════════════════

    function fillLeg(leg, legIndex) {
        const filled = [];
        const missing = [];

        // فیلد نماد
        const symbolInput = findField([
            'نماد', 'سمبل', 'instrument', 'symbol', 'کد نماد'
        ]);
        if (symbolInput) {
            if (fillField(symbolInput, leg.symbol)) {
                filled.push('symbol');
            } else {
                missing.push('symbol');
            }
        } else {
            missing.push('symbol');
        }

        // فیلد حجم
        const qtyInput = findField([
            'حجم', 'تعداد', 'quantity', 'volume'
        ]);
        if (qtyInput) {
            if (fillField(qtyInput, leg.quantity || 1)) {
                filled.push('quantity');
            }
        }

        // انتخاب Long/Short
        const sideButtons = document.querySelectorAll(
            'button, div[role="button"], label, div.buy, div.sell'
        );
        for (let i = 0; i < sideButtons.length; i++) {
            const btn = sideButtons[i];
            const txt = (btn.textContent || '').trim().toLowerCase();
            const cls = (btn.className || '').toLowerCase();

            if (leg.side === 'long' || leg.side === 'buy') {
                if (txt === 'خرید' || txt === 'buy' ||
                    cls.indexOf('buy') !== -1) {
                    btn.click();
                    filled.push('side:long');
                    break;
                }
            } else if (leg.side === 'short' || leg.side === 'sell') {
                if (txt === 'فروش' || txt === 'sell' ||
                    cls.indexOf('sell') !== -1) {
                    btn.click();
                    filled.push('side:short');
                    break;
                }
            }
        }

        return { filled: filled, missing: missing, index: legIndex };
    }

    // ═══════════════════════════════════════════════════════════
    // پیدا کردن دکمه افزودن سطر
    // ═══════════════════════════════════════════════════════════

    function findAddRowButton() {
        const selectors = [
            'button.add-row',
            'button[class*="add"]',
            'button[class*="plus"]',
            '.o-item-row button',
            'button[title*="افزودن"]',
            'button[title*="جدید"]',
            'button[aria-label*="افزودن"]',
        ];

        for (let s = 0; s < selectors.length; s++) {
            const btns = document.querySelectorAll(selectors[s]);
            for (let i = 0; i < btns.length; i++) {
                const btn = btns[i];
                if (btn.offsetParent === null || btn.disabled) continue;

                const txt = (btn.textContent || '').trim();
                const icon = btn.querySelector('i, c-k-icon');
                const iconCls = icon ? (icon.className || '') : '';

                if (txt.indexOf('+') !== -1 ||
                    txt.indexOf('افزودن') !== -1 ||
                    txt.indexOf('جدید') !== -1 ||
                    iconCls.indexOf('plus') !== -1 ||
                    iconCls.indexOf('add') !== -1) {
                    return btn;
                }
            }
        }

        // fallback: اولین دکمه‌ای که فقط + نشان می‌دهد
        const allButtons = document.querySelectorAll('button');
        for (let i = 0; i < allButtons.length; i++) {
            const btn = allButtons[i];
            if (btn.offsetParent !== null && btn.textContent.trim() === '+') {
                return btn;
            }
        }

        return null;
    }

    // ═══════════════════════════════════════════════════════════
    // sleep
    // ═══════════════════════════════════════════════════════════

    function sleep(ms) {
        return new Promise(function (resolve) {
            setTimeout(resolve, ms);
        });
    }

    // ═══════════════════════════════════════════════════════════
    // پر کردن همه لگ‌ها
    // ═══════════════════════════════════════════════════════════

    async function fillAllLegs(order) {
        const legs = order.legs || [];

        if (legs.length === 0) {
            setBannerStatus('No legs in order.', 'error');
            return;
        }

        isProcessing = true;
        console.log('[OmexSnippet] Filling ' + legs.length + ' leg(s)...');
        updateStatusBar('[OmexSnippet] Filling ' + legs.length + ' legs...');

        for (let i = 0; i < legs.length; i++) {
            const leg = legs[i];

            setBannerStatus(
                'Filling leg ' + (i + 1) + '/' + legs.length + ': ' +
                (leg.side === 'long' ? 'BUY' : 'SELL') +
                ' ' + leg.symbol,
                ''
            );

            const result = fillLeg(leg, i + 1);

            console.log(
                '[OmexSnippet] Leg ' + (i + 1) + ' filled:',
                result.filled.join(', ')
            );

            if (i < legs.length - 1) {
                await sleep(CONFIG.LEG_FILL_DELAY_MS);

                const addBtn = findAddRowButton();
                if (addBtn) {
                    console.log('[OmexSnippet] Adding new row...');
                    addBtn.click();
                    await sleep(CONFIG.ROW_ADD_DELAY_MS);
                } else {
                    console.warn('[OmexSnippet] Add row button not found');
                    setBannerStatus(
                        'Warning: Could not find "Add Row" button. ' +
                        'Please add remaining legs manually.',
                        'warning'
                    );
                }
            }
        }

        setBannerStatus(
            'All ' + legs.length + ' leg(s) filled. Please review and submit.',
            'success'
        );

        isProcessing = false;
        updateStatusBar('[OmexSnippet] Order filled at ' + new Date().toLocaleTimeString());
    }

    // ═══════════════════════════════════════════════════════════
    // نمایش بنر سفارش
    // ═══════════════════════════════════════════════════════════

    function displayOrder(order) {
        const legs = order.legs || [];

        let legsHtml = '';
        for (let i = 0; i < legs.length; i++) {
            const leg = legs[i];
            const isBuy = (leg.side === 'long' || leg.side === 'buy');
            const color = isBuy ? '#4CAF50' : '#F44336';
            const label = isBuy ? 'BUY' : 'SELL';

            legsHtml +=
                '<div class="leg-row" style="border-right: 3px solid ' + color + '; padding-right: 8px;">' +
                    '<span>' +
                        '<b style="color: ' + color + ';">' + label + '</b> ' +
                        '<span style="font-family: monospace;">' + leg.symbol + '</span>' +
                    '</span>' +
                    '<span style="background: rgba(255,255,255,0.15); padding: 2px 8px; border-radius: 4px; font-weight: bold;">' +
                        'x' + (leg.quantity || 1) +
                    '</span>' +
                '</div>';
        }

        const html =
            '<h3>New Order from UI</h3>' +
            '<div style="font-size: 12px; color: #b7e4c7; margin-bottom: 8px;">' +
                'Strategy: <b>' + (order.strategy || 'N/A') + '</b> | ' +
                'Underlying: <b>' + (order.underlying || 'N/A') + '</b>' +
            '</div>' +
            '<div class="legs-container">' + legsHtml + '</div>' +
            '<div class="status-box"></div>' +
            '<div>' +
                '<button id="omex-fill-all-btn">Fill All Legs</button>' +
                '<button id="omex-skip-btn" class="skip-btn">Skip</button>' +
            '</div>';

        const banner = showBanner(html);

        // اتصال دکمه‌ها
        const fillBtn = banner.querySelector('#omex-fill-all-btn');
        const skipBtn = banner.querySelector('#omex-skip-btn');

        if (fillBtn) {
            fillBtn.onclick = function () {
                fillAllLegs(order);
            };
        }

        if (skipBtn) {
            skipBtn.onclick = function () {
                hideBanner();
                clearPending();
            };
        }
    }

    // ═══════════════════════════════════════════════════════════
    // Pending Management
    // ═══════════════════════════════════════════════════════════

    async function clearPending() {
        try {
            await fetch(CONFIG.BRIDGE_URL + '/ack-order', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ order_id: lastOrderId })
            });
            console.log('[OmexSnippet] Order acknowledged');
        } catch (e) {
            console.error('[OmexSnippet] Clear pending failed:', e);
        }
    }

    // ═══════════════════════════════════════════════════════════
    // Poll Loop
    // ═══════════════════════════════════════════════════════════

    async function poll() {
        if (isProcessing) return;

        try {
            const response = await fetch(
                CONFIG.BRIDGE_URL + '/pending-order',
                { cache: 'no-store' }
            );

            if (!response.ok) {
                throw new Error('HTTP ' + response.status);
            }

            const data = await response.json();
            const order = data.order;

            updateStatusBar('[OmexSnippet] Active - ' + new Date().toLocaleTimeString());

            // اگر سفارشی نیست یا همان سفارش قبلی است
            if (!order) return;
            if (order.order_id === lastOrderId) return;

            // سفارش جدید!
            lastOrderId = order.order_id;
            console.log('[OmexSnippet] New order received:', order);

            playBeep();
            notify(
                'New Order',
                (order.underlying || '') + ' - ' + (order.strategy || '')
            );

            displayOrder(order);

        } catch (e) {
            // فقط خطاهای غیرشبکه‌ای را لاگ کن
            if (e.message && e.message.indexOf('Failed to fetch') === -1) {
                console.debug('[OmexSnippet] Poll error:', e.message);
            }
            updateStatusBar('[OmexSnippet] Bridge offline');
        }
    }

    // ═══════════════════════════════════════════════════════════
    // شروع
    // ═══════════════════════════════════════════════════════════

    function start() {
        console.log(
            '%c[OmexSnippet] Started',
            'color: #52b788; font-size: 16px; font-weight: bold;'
        );
        console.log('  Bridge: ' + CONFIG.BRIDGE_URL);
        console.log('  Poll interval: ' + CONFIG.POLL_INTERVAL_MS + 'ms');

        injectStyles();

        if (pollTimer) clearInterval(pollTimer);
        pollTimer = setInterval(poll, CONFIG.POLL_INTERVAL_MS);

        // اولین poll فوری
        poll();

        // اعلان شروع
        notify('OmexSnippet Ready', 'Listening for orders...');
        updateStatusBar('[OmexSnippet] Ready');
    }

    // ═══════════════════════════════════════════════════════════
    // توقف
    // ═══════════════════════════════════════════════════════════

    window.__omexSnippetStop__ = function () {
        if (pollTimer) {
            clearInterval(pollTimer);
            pollTimer = null;
        }
        hideBanner();

        const statusEl = document.getElementById('omex-snippet-status');
        if (statusEl) statusEl.remove();

        const styleEl = document.getElementById('__omex_snippet_styles__');
        if (styleEl) styleEl.remove();

        const bannerEl = document.getElementById('omex-snippet-banner');
        if (bannerEl) bannerEl.remove();

        window.__omexSnippetActive__ = false;

        console.log('%c[OmexSnippet] Stopped', 'color: #f85149; font-weight: bold;');
    };

    // ═══════════════════════════════════════════════════════════
    // اجرا
    // ═══════════════════════════════════════════════════════════

    start();

    console.log(
        '%c[OmexSnippet] To stop: window.__omexSnippetStop__()',
        'color: #8c9bae; font-style: italic;'
    );

})();