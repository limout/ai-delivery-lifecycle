/**
 * Isolated GA4 helper for the AI Delivery Copilot UI.
 * Measurement ID lives only here. This is gtag.js, not a GTM container.
 */
(function (window, document) {
    var GA4_CONFIG = {
        measurementId: "G-2ZHCXEWVMY",
        webStreamId: "15829444650",
    };

    function analyticsClientParams(search) {
        var query = search;
        if (query == null) {
            query = window.location && window.location.search ? window.location.search : "";
        }
        var raw = new URLSearchParams(query).get("client");
        if (raw == null || !String(raw).trim()) {
            return {};
        }
        if (typeof window.resolveClientName !== "function") {
            return {};
        }
        var params = {};
        params.client = window.resolveClientName(query);
        return params;
    }

    function track(eventName) {
        if (typeof window.gtag !== "function") {
            return;
        }
        window.gtag("event", eventName, analyticsClientParams());
    }

    function init() {
        if (window.__deliveryGa4Initialized) {
            return;
        }
        window.dataLayer = window.dataLayer || [];
        if (typeof window.gtag !== "function") {
            window.gtag = function gtag() {
                window.dataLayer.push(arguments);
            };
        }
        var script = document.createElement("script");
        script.async = true;
        script.src =
            "https://www.googletagmanager.com/gtag/js?id=" +
            encodeURIComponent(GA4_CONFIG.measurementId);
        document.head.appendChild(script);
        window.gtag("js", new Date());
        window.gtag("config", GA4_CONFIG.measurementId);
        window.__deliveryGa4Initialized = true;
    }

    window.DeliveryAnalytics = {
        MEASUREMENT_ID: GA4_CONFIG.measurementId,
        analyticsClientParams: analyticsClientParams,
        init: init,
        trackAnalyzeStarted: function () {
            track("analyze_started");
        },
        trackAnalyzeCompleted: function () {
            track("analyze_completed");
        },
    };

    init();
})(window, document);
