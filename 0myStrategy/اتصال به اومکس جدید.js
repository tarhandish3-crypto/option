// ============================================================
// Broker Snippet v8 — تشخیص خودکار تعداد لگ‌ها
// ============================================================
// این نسخه:
// • لیست legs را از API می‌خواند
// • تعداد سطرهای کارگزاری را تشخیص می‌دهد
// • برای هر leg یک سطر جدید ایجاد/پر می‌کند
// • پیشرفت را نمایش می‌دهد
// ============================================================

(function() {
    'use strict';
    
    // 🔒 جلوگیری از اجرای چندباره
    if (window.__BS_ACTIVE__) {
        if (window.__BS_INTERVAL__) clearInterval(window.__BS_INTERVAL__);
        const old = document.getElementById('__bs_banner');
        if (old) old.remove();
    }
    
    const API_URL = 'http://127.0.0.1:8000';
    const INTERVAL = 3000;
    
    let lastId = null;
    let banner = null;
    
    window.__BS_ACTIVE__ = true;
    
    // ═══════════════════════════════════════════════════════════
    // نمایش بنر اصلی
    // ═══════════════════════════════════════════════════════════
    
    function showBanner(order) {
        if (!banner || !document.body.contains(banner)) {
            banner = document.createElement('div');
            banner.id = '__bs_banner';
            banner.style.cssText = `
                position: fixed; top: 20px; right: 20px;
                background: linear-gradient(135deg, #203764, #2c4a80);
                color: white; padding: 18px 25px; border-radius: 12px;
                z-index: 2147483647; font-family: Tahoma; direction: rtl;
                font-size: 14px; box-shadow: 0 8px 24px rgba(0,0,0,0.4);
                border: 2px solid #4CAF50; min-width: 400px;
                max-width: 500px;
            `;
            document.body.appendChild(banner);
        }
        
        const pos = order.position;
        const legs = order.legs || [];
        const strategy = order.strategy;
        
        // ساخت نمایش لگ‌ها
        let legsHtml = '';
        legs.forEach((leg, i) => {
            const color = leg.direction === 'buy' ? '#4CAF50' : '#F44336';
            const icon = leg.direction === 'buy' ? '🟢' : '🔴';
            legsHtml += `
                <div style="
                    background:rgba(255,255,255,0.1);
                    padding:8px 12px;
                    border-radius:6px;
                    margin:4px 0;
                    border-right:4px solid ${color};
                    display:flex;
                    justify-content:space-between;
                    align-items:center;
                ">
                    <span>
                        ${icon} <b>${leg.description || leg.direction}</b>
                        <span style="font-family:monospace;margin-right:8px;">${leg.symbol}</span>
                    </span>
                    <span style="background:rgba(255,255,255,0.15);padding:2px 8px;border-radius:4px;font-weight:bold;">
                        ${leg.price.toLocaleString ? leg.price.toLocaleString('fa-IR') : leg.price}
                    </span>
                </div>
            `;
        });
        
        const strategyNames = {
            'bull_call_spread': '🐂 بول کال اسپرد',
            'covered_call': '🛡 کاورد کال',
            'long_call': '📈 لانگ کال',
        };
        
        banner.innerHTML = `
            <div style="font-size:16px;color:#4CAF50;margin-bottom:10px;">
                🎯 موقعیت از UI
            </div>
            <div style="font-size:12px;color:#8b949e;margin-bottom:8px;">
                ${strategyNames[strategy] || strategy} |
                نماد: <b>${pos.underlying}</b> |
                امتیاز: <b>${pos.composite_score}</b>
            </div>
            <div style="margin-bottom:12px;">
                <b style="font-size:13px;">📋 تعداد لگ‌ها: ${legs.length}</b>
                ${legsHtml}
            </div>
            <div id="__bs_status" style="
                margin-bottom:12px;
                padding:8px;
                background:rgba(255,255,255,0.1);
                border-radius:6px;
                font-size:12px;
                text-align:center;
                display:none;
            "></div>
            <div style="margin-top:12px;">
                <button id="__bs_fill_all" style="
                    padding:10px 20px; background:#4CAF50; color:white;
                    border:none; border-radius:6px; cursor:pointer;
                    font-family:Tahoma; font-size:14px; font-weight:bold;
                    margin:3px;
                ">✅ پر کردن همه لگ‌ها</button>
                <button id="__bs_close" style="
                    padding:10px 20px; background:#607D8B; color:white;
                    border:none; border-radius:6px; cursor:pointer;
                    font-family:Tahoma; font-size:13px; margin:3px;
                ">⏭ رد کردن</button>
            </div>
        `;
        
        document.getElementById('__bs_fill_all').onclick = () => {
            fillAllLegs(order);
        };
        
        document.getElementById('__bs_close').onclick = () => {
            closeBanner();
            clearPending();
        };
        
        banner.style.display = 'block';
        
        // صدا
        try {
            const ctx = new (window.AudioContext || window.webkitAudioContext)();
            const osc = ctx.createOscillator();
            const g = ctx.createGain();
            osc.connect(g); g.connect(ctx.destination);
            osc.frequency.value = 880;
            g.gain.setValueAtTime(0.2, ctx.currentTime);
            g.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.3);
            osc.start(); osc.stop(ctx.currentTime + 0.3);
        } catch(e) {}
    }
    
    function closeBanner() {
        if (banner) banner.style.display = 'none';
    }
    
    function setStatus(text, color = 'rgba(255,255,255,0.1)') {
        const statusEl = document.getElementById('__bs_status');
        if (statusEl) {
            statusEl.style.display = 'block';
            statusEl.style.background = color;
            statusEl.innerHTML = text;
        }
    }
    
    // ═══════════════════════════════════════════════════════════
    // پیدا کردن فیلد
    // ═══════════════════════════════════════════════════════════
    
    function findField(labels, root = document) {
        // روش ۱: label → for
        for (const lbl of root.querySelectorAll('label')) {
            const txt = (lbl.textContent || '').trim();
            if (labels.some(l => txt.includes(l))) {
                const forId = lbl.getAttribute('for');
                if (forId) {
                    const el = document.getElementById(forId);
                    if (el) return el;
                }
                const sib = lbl.parentElement?.querySelector('input, select');
                if (sib) return sib;
            }
        }
        
        // روش ۲: name/id/placeholder
        for (const inp of root.querySelectorAll('input:not([type="hidden"]), select')) {
            const attrs = [
                inp.name, inp.id, inp.placeholder,
                inp.getAttribute('aria-label')
            ].filter(Boolean).join(' ').toLowerCase();
            
            if (labels.some(l => attrs.includes(l.toLowerCase()))) return inp;
        }
        
        // روش ۳: ng-select (Angular)
        for (const inp of root.querySelectorAll('ng-select input, .ng-input input')) {
            const parent = inp.closest('ng-select, .ng-select-container');
            if (parent) {
                const parentAttrs = [
                    parent.id, parent.getAttribute('name'),
                    parent.getAttribute('formcontrolname')
                ].filter(Boolean).join(' ').toLowerCase();
                if (labels.some(l => parentAttrs.includes(l.toLowerCase()))) return inp;
            }
        }
        
        return null;
    }
    
    // ═══════════════════════════════════════════════════════════
    // پر کردن یک فیلد
    // ═══════════════════════════════════════════════════════════
    
    function fillField(input, value) {
        if (!input) return false;
        try {
            const proto = input.tagName === 'SELECT'
                ? window.HTMLSelectElement.prototype
                : window.HTMLInputElement.prototype;
            const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
            if (setter) setter.call(input, String(value));
            else input.value = String(value);
            
            ['input', 'change', 'blur'].forEach(evt => {
                input.dispatchEvent(new Event(evt, { bubbles: true }));
            });
            
            input.style.border = '3px solid #00ff00';
            setTimeout(() => { input.style.border = ''; }, 8000);
            return true;
        } catch(e) { return false; }
    }
    
    // ═══════════════════════════════════════════════════════════
    // پیدا کردن دکمه "افزودن سطر جدید" در کارگزاری
    // ═══════════════════════════════════════════════════════════
    
    function findAddRowButton() {
        // جستجوی دکمه‌های مختلف برای افزودن سطر
        const selectors = [
            'button.add-row',
            'button[class*="add"]',
            'button[class*="plus"]',
            '.o-item-row button',
            'button[title*="افزودن"]',
            'button[title*="جدید"]',
            'button[aria-label*="افزودن"]',
        ];
        
        for (const sel of selectors) {
            const btns = document.querySelectorAll(sel);
            for (const btn of btns) {
                const txt = (btn.textContent || '').trim();
                const icon = btn.querySelector('i, c-k-icon')?.className || '';
                // دکمه‌هایی که آیکون + دارند یا متن افزودن
                if (txt.includes('+') || txt.includes('افزودن') || 
                    txt.includes('جدید') || icon.includes('plus') || 
                    icon.includes('add')) {
                    // بررسی اینکه دکمه مخفی یا غیرفعال نباشد
                    if (btn.offsetParent !== null && !btn.disabled) {
                        return btn;
                    }
                }
            }
        }
        
        // اگر پیدا نشد، اولین دکمه‌ای که فقط + نشان می‌دهد
        const allButtons = document.querySelectorAll('button');
        for (const btn of allButtons) {
            if (btn.textContent.trim() === '+' && btn.offsetParent !== null) {
                return btn;
            }
        }
        
        return null;
    }
    
    // ═══════════════════════════════════════════════════════════
    // پیدا کردن آخرین سطر فرم
    // ═══════════════════════════════════════════════════════════
    
    function findLastFormRow() {
        // پیدا کردن تمام سطرهای فرم
        const rowSelectors = [
            'div.o-item-row',
            'div[class*="order-row"]',
            'div[class*="form-row"]',
            'div[class*="leg-row"]',
            'table tbody tr',
        ];
        
        for (const sel of rowSelectors) {
            const rows = document.querySelectorAll(sel);
            if (rows.length > 0) {
                return rows[rows.length - 1];
            }
        }
        
        return null;
    }
    
    // ═══════════════════════════════════════════════════════════
    // پر کردن یک لگ (سطر)
    // ═══════════════════════════════════════════════════════════
    
    async function fillLeg(leg, legIndex, totalLegs) {
        console.log(`[BS] Filling leg ${legIndex}/${totalLegs}:`, leg);
        
        const filled = [];
        const missing = [];
        
        // پیدا کردن فیلدها در کل صفحه
        const symField = findField(['نماد', 'سمبل', 'symbol', 'کد نماد']);
        const priceField = findField(['قیمت', 'مبلغ', 'price']);
        const volField = findField(['حجم', 'تعداد', 'quantity']);
        
        if (fillField(symField, leg.symbol)) filled.push('نماد');
        else missing.push('نماد');
        
        if (fillField(priceField, leg.price)) filled.push('قیمت');
        else missing.push('قیمت');
        
        if (fillField(volField, leg.quantity || 1)) filled.push('حجم');
        else missing.push('حجم');
        
        // ⚠️ اگر فروش است، دکمه sell را باید بزنیم
        if (leg.direction === 'sell') {
            const sellBtn = findSellButton();
            if (sellBtn) {
                sellBtn.click();
                filled.push('فروش');
            }
        } else {
            const buyBtn = findBuyButton();
            if (buyBtn) {
                buyBtn.click();
                filled.push('خرید');
            }
        }
        
        return { filled, missing };
    }
    
    // ═══════════════════════════════════════════════════════════
    // پیدا کردن دکمه خرید/فروش
    // ═══════════════════════════════════════════════════════════
    
    function findBuyButton() {
        const selectors = [
            'div.buy',
            'button.buy',
            '[class*="buy"]',
        ];
        
        for (const sel of selectors) {
            const btns = document.querySelectorAll(sel);
            for (const btn of btns) {
                if (btn.offsetParent !== null) {
                    const cls = btn.className || '';
                    // اگر فعال نیست، کلیک کن
                    if (!cls.includes('isActive') && !cls.includes('active')) {
                        return btn;
                    }
                }
            }
        }
        return null;
    }
    
    function findSellButton() {
        const selectors = [
            'div.sell',
            'button.sell',
            '[class*="sell"]',
        ];
        
        for (const sel of selectors) {
            const btns = document.querySelectorAll(sel);
            for (const btn of btns) {
                if (btn.offsetParent !== null) {
                    const cls = btn.className || '';
                    if (!cls.includes('isActive') && !cls.includes('active')) {
                        return btn;
                    }
                }
            }
        }
        return null;
    }
    
    // ═══════════════════════════════════════════════════════════
    // 🎯 پر کردن همه لگ‌ها به ترتیب
    // ═══════════════════════════════════════════════════════════
    
    async function fillAllLegs(order) {
        const legs = order.legs || [];
        
        if (legs.length === 0) {
            setStatus('⚠️ لگی وجود ندارد', 'rgba(255,152,0,0.3)');
            return;
        }
        
        console.log(`[BS] Starting to fill ${legs.length} legs...`);
        
        const btn = document.getElementById('__bs_fill_all');
        if (btn) {
            btn.disabled = true;
            btn.textContent = '⏳ در حال پر کردن...';
        }
        
        for (let i = 0; i < legs.length; i++) {
            const leg = legs[i];
            
            // نمایش وضعیت
            setStatus(
                `⏳ در حال پر کردن لگ ${i + 1} از ${legs.length}:<br>` +
                `<b>${leg.direction === 'buy' ? '🟢 خرید' : '🔴 فروش'}</b> ` +
                `<b>${leg.symbol}</b> @ <b>${leg.price}</b>`
            );
            
            // پر کردن این لگ
            const result = await fillLeg(leg, i + 1, legs.length);
            
            // نمایش نتیجه
            const statusColor = result.missing.length === 0 
                ? 'rgba(76,175,80,0.3)' 
                : 'rgba(255,152,0,0.3)';
            
            setStatus(
                `✅ لگ ${i + 1}/${legs.length}: ` +
                `${result.filled.join('، ')}` +
                (result.missing.length > 0 
                    ? `<br>⚠️ یافت نشد: ${result.missing.join('، ')}` 
                    : ''),
                statusColor
            );
            
            // اگر لگ آخر نیست، یک سطر جدید اضافه کن
            if (i < legs.length - 1) {
                await sleep(500);
                
                const addBtn = findAddRowButton();
                if (addBtn) {
                    console.log(`[BS] Adding new row...`);
                    addBtn.click();
                    await sleep(800);
                    setStatus(
                        `✅ لگ ${i + 1} پر شد. سطر جدید اضافه شد...<br>` +
                        `⏳ آماده برای لگ ${i + 2}`
                    );
                } else {
                    console.warn('[BS] Add row button not found');
                    setStatus(
                        `⚠️ دکمه "افزودن سطر" پیدا نشد.<br>` +
                        `لطفاً لگ ${i + 2} را دستی وارد کنید.`,
                        'rgba(255,152,0,0.3)'
                    );
                }
            } else {
                // لگ آخر
                await sleep(500);
                setStatus(
                    `✅ همه ${legs.length} لگ پر شد!<br>` +
                    `لطفاً بررسی و ثبت کنید.`,
                    'rgba(76,175,80,0.3)'
                );
                
                // پاک کردن pending
                setTimeout(() => {
                    clearPending();
                }, 3000);
            }
        }
        
        if (btn) {
            btn.disabled = false;
            btn.textContent = '✅ پر کردن همه لگ‌ها';
        }
    }
    
    function sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
    
    // ═══════════════════════════════════════════════════════════
    // Pending
    // ═══════════════════════════════════════════════════════════
    
    async function clearPending() {
        try {
            await fetch(`${API_URL}/clear-pending`, { method: 'POST' });
        } catch(e) {}
    }
    
    async function checkPending() {
        try {
            const r = await fetch(`${API_URL}/pending-order`, { cache: 'no-store' });
            const data = await r.json();
            
            if (!data.pending_order) return;
            
            const order = data.pending_order;
            if (order.id === lastId) return;
            
            console.log('[BS] New order:', order.strategy);
            console.log('[BS] Legs count:', (order.legs || []).length);
            
            showBanner(order);
            lastId = order.id;
            
        } catch(e) {}
    }
    
    // ═══════════════════════════════════════════════════════════
    // شروع
    // ═══════════════════════════════════════════════════════════
    
    console.log('🟢 [BS] Broker Snippet v8 started');
    console.log('   API:', API_URL);
    console.log('   Features: multi-leg support, auto-detect legs count');
    
    setTimeout(checkPending, 1000);
    window.__BS_INTERVAL__ = setInterval(checkPending, INTERVAL);
    
    window.__BS_STOP__ = function() {
        if (window.__BS_INTERVAL__) clearInterval(window.__BS_INTERVAL__);
        const b = document.getElementById('__bs_banner');
        if (b) b.remove();
        window.__BS_ACTIVE__ = false;
        console.log('✅ [BS] Stopped');
    };
    
    console.log('💡 برای توقف: window.__BS_STOP__()');
    
})();