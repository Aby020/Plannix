// Disabling Developer Option

    /* ========== 1) Disable context menu (right click) ========== */
    document.addEventListener('contextmenu', e => e.preventDefault());

    /* ========== 2) Disable common hotkeys (F12, Ctrl+Shift+I/J, Ctrl+U, Ctrl+S) ========== */
    document.addEventListener('keydown', function(e) {
    // key codes: 123 = F12, 73 = I, 74 = J, 85 = U, 83 = S
    if (e.keyCode === 123) e.preventDefault(); // F12
    if (e.ctrlKey && e.shiftKey && (e.keyCode === 73 || e.keyCode === 74)) e.preventDefault();
    if (e.ctrlKey && (e.keyCode === 85 || e.keyCode === 83)) e.preventDefault();
    });

    /* ========== 3) Detect DevTools and react ========== */
    /* multiple techniques combined: resize heuristic + toString trick + debugger detection */
    (function() {
    const overlay = document.getElementById('devBlockOverlay');
    let devtoolsOpen = false;
    const showOverlay = () => {
        devtoolsOpen = true;
        overlay.style.display = 'flex';
        try { window.stop && window.stop(); } catch(e){}
    };
    const hideOverlay = () => {
        devtoolsOpen = false;
        overlay.style.display = 'none';
    };

    // Heuristic: large difference between outer and inner dims (common when docked)
    function checkSize() {
        const threshold = 160; // pixels
        if (Math.abs(window.outerWidth - window.innerWidth) > threshold ||
            Math.abs(window.outerHeight - window.innerHeight) > threshold) {
        if (!devtoolsOpen) showOverlay();
        } else {
        if (devtoolsOpen) hideOverlay();
        }
    }
    window.addEventListener('resize', checkSize);
    setInterval(checkSize, 700);

    // toString trick (less reliable but helpful)
    let element = new Image();
    Object.defineProperty(element, 'id', {
        get: function() {
        showOverlay();
        return '';
        }
    });

    console.log('%c', element); // console access may trigger getter if console open

    // debugger detection: tries to trigger a pause and checks timing
    let last = Date.now();
    function detectDebugger() {
        const start = Date.now();
        debugger; // will pause if DevTools is set to pause on exceptions/has breakpoints
        const end = Date.now();
        if (end - start > 100) { // arbitrary threshold; large pause implies devtools debugging
        showOverlay();
        }
        last = Date.now();
    }
    try {
        // run occasionally — don't run too often or it annoys users
        setInterval(detectDebugger, 3000);
    } catch (e) { /* ignore */ }

    })();

    /* ========== 4) Hide source via obfuscation suggestion (client-side only) ==========
    In production, build with a bundler and enable minify/uglify/obfuscate and do NOT ship source maps.
    Example: remove source maps, enable terser/obfuscator in your build pipeline.
    */

    /* ========== 5) Anti-inspect: redefine console methods to make printing harder ========== */
    (function() {
    try {
        const methods = ['log','warn','debug','info','error','table'];
        methods.forEach(m => {
        const orig = console[m];
        Object.defineProperty(console, m, {
            configurable: true,
            enumerable: false,
            writable: false,
            value: function() {
            // optional: no-op or forward conditionally
            // orig.apply(console, arguments); // forward only in dev builds
            }
        });
        });
    } catch(e) {}
    })()