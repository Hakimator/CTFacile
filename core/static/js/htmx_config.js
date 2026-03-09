document.addEventListener('htmx:configRequest', (event) => {
    const csrfInput = document.querySelector('[name=csrfmiddlewaretoken]');
    if (csrfInput && event.detail && event.detail.headers) {
        event.detail.headers['X-CSRFToken'] = csrfInput.value;
    }
});

document.addEventListener('htmx:responseError', async function (evt) {
    const status = evt.detail.xhr.status;

    // 401 Unauthorized Interceptor
    // If our HttpOnly JWT access token expires during an HTMX request
    if (status === 401) {
        console.warn("HTMX Request blocked. Attempting to refresh Auth Token silently...");
        
        // Pause HTMX, send a vanilla fetch to the refresh endpoint (which reads the HttpOnly cookie implicitly)
        try {
            const refreshRes = await fetch('/api/v1/auth/refresh/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            if (refreshRes.ok) {
                // The refresh worked, the backend sent a new HttpOnly access token.
                // Replay the exact same HTMX request that failed originally.
                htmx.ajax(evt.detail.requestConfig.verb, evt.detail.requestConfig.path, {
                    target: evt.detail.target,
                    swap: evt.detail.requestConfig.swap
                });
            } else {
                // The refresh token itself is dead. Nuke the session and force ungraceful login.
                console.error("Refresh token dead. Redirecting to login.");
                window.location.href = '/login/';
            }
        } catch (error) {
            console.error("Network error during token refresh. Check connection.");
        }
    }
});
